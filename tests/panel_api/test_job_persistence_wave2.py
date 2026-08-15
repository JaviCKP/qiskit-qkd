from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from panel.api.app import create_app
from panel.api.artifact_store import ArtifactStoreError
from panel.api.job_store import (
    JOB_DB_SCHEMA_VERSION,
    JobStore,
    JobStoreError,
    JobStoreVersionError,
)
from panel.api.jobs import JobCapacityError, JobControl, JobManager, JobRecord
from qiskit_qkd.config import Scenario


def _fast_job() -> dict[str, bool]:
    return {"ok": True}


def _slow_sweep_job(*, job_control: object) -> dict[str, bool]:
    del job_control
    time.sleep(0.3)
    return {"ok": True}


def _blocked_job() -> None:
    while True:
        time.sleep(0.1)


def _cooperative_batch_job(steps: int, *, job_control: JobControl) -> int:
    for index in range(steps):
        job_control.checkpoint()
        time.sleep(0.01)
        job_control.report(index + 1)
    return steps


def _wait_for(manager: JobManager, job_id: str, status: str, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = manager.get(job_id)
        assert record is not None
        if record.status == status:
            return record
        time.sleep(0.02)
    pytest.fail(f"job {job_id} did not reach {status!r}")


def test_completed_result_survives_restart_without_metadata_payload(
    tmp_path: Path,
) -> None:
    manager = JobManager(
        use_processes=False,
        store_dir=tmp_path,
        inline_result_bytes=8,
    )
    record = manager.submit("run", lambda: {"payload": "x" * 500}, digest="d" * 64)
    assert record.status == "done"
    assert record.result is None
    manager.shutdown()

    db = tmp_path / "jobs.sqlite3"
    assert db.exists()
    assert json.loads(next((tmp_path / "artifacts").glob("*.json")).read_text())[
        "payload"
    ]
    restarted = JobManager(
        use_processes=False, store_dir=tmp_path, inline_result_bytes=8
    )
    restored = restarted.get(record.job_id)
    assert restored is not None
    assert restored.status == "done"
    assert restored.digest == "d" * 64
    assert restored.get_result()["payload"] == "x" * 500
    assert restored.result is None
    restarted.shutdown()


def test_status_summary_survives_restart_without_loading_large_artifact(
    tmp_path: Path,
) -> None:
    manager = JobManager(
        use_processes=False,
        store_dir=tmp_path,
        inline_result_bytes=8,
    )
    record = manager.submit(
        "run",
        lambda: {
            "result_summary": {"metrics": {"qber": 0.01}},
            "result": {"event_sample": [{"payload": "x" * 500}]},
        },
    )
    manager.shutdown()

    restarted = JobManager(
        use_processes=False,
        store_dir=tmp_path,
        inline_result_bytes=8,
    )
    restored = restarted.get(record.job_id)
    assert restored is not None
    assert restored.result is None
    restored.artifact_loader = lambda _record: pytest.fail(
        "status polling loaded the result artifact"
    )
    assert restored.to_status()["result_summary"] == {
        "metrics": {"qber": 0.01}
    }
    restarted.shutdown()


def test_artifact_write_failure_corrects_provisional_done_to_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = JobManager(use_processes=False, store_dir=tmp_path)
    assert manager._artifacts is not None

    def fail_write(_job_id: str, _payload: object) -> None:
        raise ArtifactStoreError("disk full")

    monkeypatch.setattr(manager._artifacts, "write_json", fail_write)
    record = manager.submit("run", _fast_job)
    assert record.status == "error"
    assert record.error_code == "ARTIFACT_WRITE_FAILED"
    assert record.result is None
    manager.shutdown()


def test_artifact_retention_is_least_recently_used(tmp_path: Path) -> None:
    manager = JobManager(
        use_processes=False,
        store_dir=tmp_path,
        inline_result_bytes=0,
        max_retention_bytes=1_000_000,
    )
    first = manager.submit("run", lambda: {"payload": "a" * 500})
    second = manager.submit("run", lambda: {"payload": "b" * 500})
    assert first.artifact_size_bytes > 0
    assert second.artifact_size_bytes > 0

    assert first.get_result()["payload"].startswith("a")
    manager.max_retention_bytes = max(
        first.artifact_size_bytes,
        second.artifact_size_bytes,
    )
    manager.cleanup()

    assert manager.get(first.job_id) is not None
    assert manager.get(second.job_id) is None
    manager.shutdown()


def test_job_store_migrates_v1_and_rejects_future_schema(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    store = JobStore(database)
    assert store.connection is not None
    store.connection.execute("PRAGMA user_version = 1")
    store.close()

    migrated = JobStore(database)
    assert migrated.connection is not None
    version = migrated.connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == JOB_DB_SCHEMA_VERSION
    columns = {
        row[1]
        for row in migrated.connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    assert {"result_summary_json", "last_accessed_at_utc"} <= columns
    migrated.close()

    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(
                f"PRAGMA user_version = {JOB_DB_SCHEMA_VERSION + 1}"
            )
    with pytest.raises(JobStoreVersionError, match="newer than supported"):
        JobStore(database)


def test_corrupt_job_row_is_skipped_without_aborting_startup(tmp_path: Path) -> None:
    manager = JobManager(use_processes=False, store_dir=tmp_path)
    record = manager.submit("run", _fast_job)
    manager.shutdown()

    database = tmp_path / "jobs.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(
                "UPDATE jobs SET progress_done='not-an-integer' WHERE job_id=?",
                (record.job_id,),
            )

    restarted = JobManager(use_processes=False, store_dir=tmp_path)
    assert restarted.get(record.job_id) is None
    assert any(
        "corrupt job metadata row" in item
        for item in restarted.degraded_reasons
    )
    restarted.shutdown()


def test_job_row_with_non_object_issue_is_skipped_without_status_crash(
    tmp_path: Path,
) -> None:
    manager = JobManager(use_processes=False, store_dir=tmp_path)
    record = manager.submit("run", _fast_job)
    manager.shutdown()

    database = tmp_path / "jobs.sqlite3"
    with closing(sqlite3.connect(database)) as connection:
        with connection:
            connection.execute(
                "UPDATE jobs SET issues_json='[\"bad\"]' WHERE job_id=?",
                (record.job_id,),
            )

    restarted = JobManager(use_processes=False, store_dir=tmp_path)
    assert restarted.get(record.job_id) is None
    assert restarted.list() == []
    assert any(
        "corrupt job metadata row" in item
        for item in restarted.degraded_reasons
    )
    restarted.shutdown()


def test_artifact_delete_failure_keeps_metadata_tracked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = JobManager(
        use_processes=False,
        store_dir=tmp_path,
        inline_result_bytes=0,
    )
    record = manager.submit("run", _fast_job)
    assert manager._artifacts is not None

    def fail_delete(_job_id: str) -> bool:
        raise ArtifactStoreError("simulated locked artifact")

    monkeypatch.setattr(manager._artifacts, "delete", fail_delete)
    manager.max_retention_bytes = 0
    manager.cleanup()

    assert manager.get(record.job_id) is record
    assert manager._store is not None
    assert [item.job_id for item in manager._store.load_all()] == [record.job_id]
    manager.shutdown()


def test_artifact_reference_recovers_after_second_phase_metadata_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = JobManager(
        use_processes=False,
        store_dir=tmp_path,
        inline_result_bytes=0,
    )
    assert manager._store is not None
    original_upsert = manager._store.upsert
    failed = False

    def fail_final_reference(record: JobRecord) -> None:
        nonlocal failed
        if record.status == "done" and record.artifact_path is not None and not failed:
            failed = True
            raise JobStoreError("simulated reference commit failure")
        original_upsert(record)

    monkeypatch.setattr(manager._store, "upsert", fail_final_reference)
    record = manager.submit("run", _fast_job)
    assert failed is True
    assert record.result is not None
    assert record.artifact_path is not None
    manager._store.close()

    restarted = JobManager(use_processes=False, store_dir=tmp_path)
    restored = restarted.get(record.job_id)
    assert restored is not None
    assert restored.artifact_path is not None
    assert restored.get_result() == {"ok": True}
    restarted.shutdown()
    manager.shutdown()


def test_active_metadata_is_marked_interrupted_on_restart(tmp_path: Path) -> None:
    manager = JobManager(use_processes=False, store_dir=tmp_path)
    record = JobRecord(
        job_id="r_active",
        kind="run",
        status="queued",
        progress={"done": 0, "total": 1},
        created_at=time.monotonic(),
        persist_callback=manager._persist_record,
    )
    manager._records[record.job_id] = record
    manager._persist_record(record)
    # Simulate a process crash: leave the queued metadata durable but do not
    # run the normal shutdown transition that would mark it cancelled.
    assert manager._store is not None
    manager._store.close()

    restarted = JobManager(use_processes=False, store_dir=tmp_path)
    restored = restarted.get(record.job_id)
    assert restored is not None
    assert restored.status == "interrupted"
    assert restored.error_code == "INTERRUPTED"
    restarted.shutdown()


def test_corrupt_artifact_does_not_break_job_listing(tmp_path: Path) -> None:
    manager = JobManager(use_processes=False, store_dir=tmp_path, inline_result_bytes=0)
    record = manager.submit("run", _fast_job)
    manager.shutdown()
    next((tmp_path / "artifacts").glob("*.json")).write_text("not-json")

    restarted = JobManager(use_processes=False, store_dir=tmp_path)
    restored = restarted.get(record.job_id)
    assert restored is not None
    assert restored.to_status()["status"] == "done"
    assert restored.get_result() is None
    assert restored.error_code == "ARTIFACT_CORRUPTED"
    assert restarted.list()
    restarted.shutdown()


def test_queue_budget_rejects_cost_and_bytes_without_evicting_active() -> None:
    manager = JobManager(use_processes=False, max_queue_cost=3.0, max_queue_bytes=10)
    active = JobRecord(
        job_id="r_active",
        kind="run",
        status="running",
        progress={"done": 0, "total": 1},
        created_at=time.monotonic(),
        cost=3.0,
        estimated_bytes=10,
    )
    manager._records[active.job_id] = active
    with pytest.raises(JobCapacityError, match="cost budget"):
        manager.submit("run", _fast_job, cost=1.0)
    assert manager.get(active.job_id) is active
    manager.shutdown()


def test_process_pools_keep_cheap_run_available_while_sweep_runs() -> None:
    manager = JobManager(use_processes=True, max_workers=2, timeout_s=5.0)
    try:
        sweep = manager.submit("sweep", _slow_sweep_job, total=1)
        run = manager.submit("run", _fast_job, total=1)
        _wait_for(manager, run.job_id, "done")
        _wait_for(manager, sweep.job_id, "done")
    finally:
        manager.shutdown()


def test_cancel_during_batch_reaches_terminal_within_grace() -> None:
    manager = JobManager(
        use_processes=True,
        max_workers=2,
        timeout_s=5.0,
        cancellation_grace_s=0.2,
    )
    try:
        record = manager.submit("run", _cooperative_batch_job, 200, total=200)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            current = manager.get(record.job_id)
            assert current is not None
            if current.status == "running" and current.progress["done"] > 0:
                break
            time.sleep(0.02)
        assert manager.cancel(record.job_id) is False
        terminal = _wait_for(manager, record.job_id, "cancelled", timeout=3.0)
        assert terminal.error_code == "CANCELLED"
    finally:
        manager.shutdown()


def test_timeout_terminates_only_main_pool_and_recreates_it() -> None:
    manager = JobManager(
        use_processes=True,
        max_workers=2,
        timeout_s=2.0,
        timeout_grace_s=0.1,
    )
    try:
        blocked = manager.submit("run", _blocked_job)
        sweep = manager.submit("sweep", _fast_job)
        _wait_for(manager, blocked.job_id, "timed_out", timeout=5.0)
        assert blocked.error_code == "TIMED_OUT"
        _wait_for(manager, sweep.job_id, "done")
        replacement = manager.submit("run", _fast_job)
        _wait_for(manager, replacement.job_id, "done", timeout=5.0)
    finally:
        started = time.monotonic()
        manager.shutdown()
        assert time.monotonic() - started < 3.0


def test_shutdown_with_blocked_worker_is_bounded() -> None:
    manager = JobManager(use_processes=True, max_workers=2, timeout_s=30.0)
    record = manager.submit("run", _blocked_job)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        current = manager.get(record.job_id)
        assert current is not None
        if current.status == "running":
            break
        time.sleep(0.02)
    else:
        manager.shutdown()
        pytest.fail("blocked worker did not start before shutdown test")
    started = time.monotonic()
    manager.shutdown()
    assert time.monotonic() - started < 3.0


def test_two_concurrent_jobs_reach_done() -> None:
    manager = JobManager(use_processes=True, max_workers=2, timeout_s=5.0)
    try:
        first = manager.submit("run", _fast_job)
        second = manager.submit("sweep", _fast_job)
        _wait_for(manager, first.job_id, "done")
        _wait_for(manager, second.job_id, "done")
    finally:
        manager.shutdown()


def test_readiness_reports_live_and_ready_dependencies(tmp_path: Path) -> None:
    app = create_app(store_dir=tmp_path, use_processes=False)
    with TestClient(app) as client:
        assert client.get("/api/health/live").status_code == 200
        response = client.get("/api/health/ready")
        assert response.status_code == 200
        payload = response.json()
        assert payload["ready"] is True
        assert payload["dependencies"]["job_manager"] is True


def test_create_run_preserves_unsupported_scenario_version_details(
    tmp_path: Path,
) -> None:
    payload = Scenario(pulses=1, clock_rate_hz=1_000_000.0, seed=1).to_dict()
    payload["schema_version"] = 999
    app = create_app(store_dir=tmp_path, use_processes=False)
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"scenario": payload})
    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["found_version"] == 999
    assert issue["supported_versions"] == [1, 2]
    assert "schema version" in issue["suggestion"].lower()


def test_terminal_log_record_has_stable_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="panel.api.jobs")
    manager = JobManager(use_processes=False)
    manager.submit("run", _fast_job, digest="a" * 64, cost=2.0, estimated_bytes=32)
    manager.shutdown()
    queued = [
        record for record in caplog.records if record.getMessage() == "job terminal"
    ]
    assert queued
    assert queued[-1].job_id.startswith("r_")
    assert queued[-1].kind == "run"
    assert queued[-1].digest == "a" * 64
    assert queued[-1].status == "done"
