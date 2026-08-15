from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from queue import SimpleQueue
from threading import Event

import pytest

from panel.api.jobs import (
    CooperativeCancellation,
    JobCapacityError,
    JobControl,
    JobManager,
    JobManagerShutdownError,
    JobRecord,
)
from panel.api.runtime import sweep_scenario_job
from qiskit_qkd.config import Scenario


def _slow_controlled_job(steps: int, *, job_control: JobControl) -> int:
    completed = 0
    for completed in range(1, steps + 1):
        job_control.checkpoint()
        time.sleep(0.01)
        job_control.report(completed)
    return completed


class _CancellingProgressQueue:
    def __init__(self, event: Event) -> None:
        self.event = event
        self.values: list[int] = []

    def put(self, value: int) -> None:
        self.values.append(value)
        self.event.set()


def _record_with_future(future: Future[object]) -> JobRecord:
    return JobRecord(
        job_id="r_test",
        kind="run",
        status="queued",
        progress={"done": 0, "total": 1},
        created_at=time.monotonic(),
        future=future,
    )


def test_cancel_does_not_claim_a_running_future_was_cancelled() -> None:
    manager = JobManager(use_processes=False)
    future: Future[object] = Future()
    assert future.set_running_or_notify_cancel() is True
    record = _record_with_future(future)
    manager._records[record.job_id] = record

    assert manager.cancel(record.job_id, kind="run") is False
    assert record.status == "running"
    assert future.cancelled() is False


def test_cancel_reports_success_only_for_a_future_it_cancelled() -> None:
    manager = JobManager(use_processes=False)
    future: Future[object] = Future()
    record = _record_with_future(future)
    manager._records[record.job_id] = record

    assert manager.cancel(record.job_id, kind="run") is True
    assert record.status == "cancelled"
    assert future.cancelled() is True


def test_refresh_preserves_an_externally_cancelled_future_state() -> None:
    future: Future[object] = Future()
    assert future.cancel() is True
    record = _record_with_future(future)

    record.refresh()

    assert record.status == "cancelled"
    assert record.error is None


def test_manager_lookup_and_cancel_are_kind_safe() -> None:
    manager = JobManager(use_processes=False)
    record = manager.submit("run", lambda: {"ok": True})

    assert manager.get(record.job_id, kind="sweep") is None
    assert manager.cancel(record.job_id, kind="sweep") is False
    assert manager.get(record.job_id, kind="run") is record
    assert record.to_status()["kind"] == "run"


def test_running_cooperative_job_reports_cancellation_requested_honestly() -> None:
    manager = JobManager(use_processes=False)
    future: Future[object] = Future()
    assert future.set_running_or_notify_cancel() is True
    record = _record_with_future(future)
    record.cancellation_event = Event()
    manager._records[record.job_id] = record

    assert manager.cancel(record.job_id, kind="run") is False
    assert record.status == "cancellation_requested"
    assert record.cancellation_event.is_set() is True
    assert future.cancelled() is False


def test_completion_wins_if_worker_finishes_during_cancellation_request() -> None:
    manager = JobManager(use_processes=False)
    future: Future[object] = Future()
    assert future.set_running_or_notify_cancel() is True
    record = _record_with_future(future)
    record.cancellation_event = Event()
    manager._records[record.job_id] = record

    assert manager.cancel(record.job_id, kind="run") is False
    future.set_result({"ok": True})

    assert manager.get(record.job_id, kind="run") is record
    assert record.status == "done"
    assert record.result == {"ok": True}


def test_worker_error_is_sanitized_at_the_public_boundary() -> None:
    def fail() -> None:
        raise RuntimeError("secret=C:/private/credential.txt")

    manager = JobManager(use_processes=False)
    record = manager.submit("run", fail)

    assert record.status == "error"
    assert record.error == "The job failed; consult server logs for details."
    assert "private" not in record.to_status()["error"]


def test_cleanup_expires_results_then_removes_old_tombstones() -> None:
    manager = JobManager(
        use_processes=False,
        retention_s=10.0,
        expired_tombstone_s=5.0,
    )
    record = manager.submit("run", lambda: {"large": "payload"})
    assert record.status == "done"
    assert record.terminal_at is not None
    expiry_now = record.terminal_at + 10.1

    cleanup = manager.cleanup(now=expiry_now)

    assert cleanup == {"expired": 1, "removed": 0}
    assert record.status == "expired"
    assert record.result is None
    assert manager.get(record.job_id) is record

    cleanup = manager.cleanup(now=expiry_now + 5.1)

    assert cleanup == {"expired": 0, "removed": 1}
    assert manager.get(record.job_id) is None


def test_progress_updates_are_monotonic_and_bounded() -> None:
    future: Future[object] = Future()
    assert future.set_running_or_notify_cancel() is True
    record = _record_with_future(future)
    record.progress = {"done": 0, "total": 4}
    progress: SimpleQueue[int] = SimpleQueue()
    record.progress_queue = progress
    for value in (1, 3, 2, 99):
        progress.put(value)

    record.refresh()

    assert record.progress == {"done": 4, "total": 4}


def test_timeout_requests_cooperative_cancellation_without_false_terminal_state(
) -> None:
    manager = JobManager(use_processes=False, timeout_s=5.0)
    future: Future[object] = Future()
    assert future.set_running_or_notify_cancel() is True
    record = _record_with_future(future)
    record.status = "running"
    record.started_at = time.monotonic() - 6.0
    record.timeout_s = 5.0
    record.cancellation_event = Event()
    manager._records[record.job_id] = record

    manager.get(record.job_id)

    assert record.status == "cancellation_requested"
    assert record.cancellation_event.is_set() is True
    assert record.timed_out is True


def test_active_job_capacity_is_bounded() -> None:
    manager = JobManager(use_processes=False, max_active_jobs=1)
    future: Future[object] = Future()
    manager._records["r_active"] = _record_with_future(future)

    with pytest.raises(JobCapacityError, match="active-job limit"):
        manager.submit("run", lambda: None)


def test_shutdown_is_idempotent_and_rejects_new_work() -> None:
    manager = JobManager(use_processes=False)

    manager.shutdown()
    manager.shutdown()

    with pytest.raises(JobManagerShutdownError, match="shut down"):
        manager.submit("run", lambda: None)


def test_two_concurrent_queries_observe_a_consistent_record() -> None:
    manager = JobManager(use_processes=False)
    future: Future[object] = Future()
    assert future.set_running_or_notify_cancel() is True
    record = _record_with_future(future)
    manager._records[record.job_id] = record

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(
            executor.map(
                lambda _index: manager.get(record.job_id).to_status()["status"],
                range(50),
            ),
        )

    assert statuses == ["running"] * 50
    timestamps = record.to_status()["timestamps"]
    assert timestamps["created_at"] is not None
    assert timestamps["updated_at"] is not None


def test_cancel_cannot_race_a_future_assignment() -> None:
    manager = JobManager(use_processes=False)
    submit_entered = Event()
    release_submit = Event()
    pending_future: Future[object] = Future()

    class BlockingExecutor:
        def submit(self, *_args: object) -> Future[object]:
            submit_entered.set()
            assert release_submit.wait(timeout=2.0)
            return pending_future

    manager._executor = BlockingExecutor()  # type: ignore[assignment]
    manager._new_worker_channels = lambda: (Event(), SimpleQueue())  # type: ignore[method-assign]
    manager._start_monitor_locked = lambda: None  # type: ignore[method-assign]

    with ThreadPoolExecutor(max_workers=2) as executor:
        submitted = executor.submit(manager.submit, "run", lambda: None)
        assert submit_entered.wait(timeout=2.0)
        job_id = next(iter(manager._records))
        cancel_started = Event()

        def cancel_during_submit() -> bool:
            cancel_started.set()
            return manager.cancel(job_id)

        cancelled = executor.submit(cancel_during_submit)
        assert cancel_started.wait(timeout=2.0)
        time.sleep(0.01)
        release_submit.set()
        record = submitted.result(timeout=2.0)
        assert cancelled.result(timeout=2.0) is True

    assert pending_future.cancelled() is True
    assert record.status == "cancelled"


def test_sweep_worker_reports_progress_after_every_protocol_evaluation() -> None:
    progress: SimpleQueue[int] = SimpleQueue()
    control = JobControl(Event(), progress, total=4)
    scenario = Scenario(pulses=4, clock_rate_hz=1_000_000.0, seed=9)

    result = sweep_scenario_job(
        scenario.to_dict(),
        {"target": "scenario.pulses", "values": [4, 5]},
        None,
        2,
        job_control=control,
    )

    assert len(result["rows"]) == 4
    assert [progress.get_nowait() for _index in range(4)] == [1, 2, 3, 4]


def test_sweep_observes_cooperative_cancellation_between_evaluations() -> None:
    cancellation = Event()
    progress = _CancellingProgressQueue(cancellation)
    control = JobControl(cancellation, progress, total=3)
    scenario = Scenario(pulses=4, clock_rate_hz=1_000_000.0, seed=9)

    with pytest.raises(CooperativeCancellation):
        sweep_scenario_job(
            scenario.to_dict(),
            {"target": "scenario.pulses", "values": [4, 5, 6]},
            None,
            1,
            job_control=control,
        )

    assert progress.values == [1]


def test_process_worker_cancels_cooperatively_and_leaves_no_live_work() -> None:
    manager = JobManager(
        use_processes=True,
        max_workers=1,
        timeout_s=10.0,
    )
    try:
        record = manager.submit("sweep", _slow_controlled_job, 200, total=200)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            current = manager.get(record.job_id)
            assert current is not None
            if current.status == "running" and current.progress["done"] >= 1:
                break
            time.sleep(0.01)
        else:
            pytest.fail("process worker did not start before the deadline")

        assert manager.cancel(record.job_id) is False
        assert record.status == "cancellation_requested"
        while time.monotonic() < deadline:
            current = manager.get(record.job_id)
            assert current is not None
            if current.status == "cancelled":
                break
            time.sleep(0.01)
        else:
            pytest.fail("process worker did not acknowledge cancellation")

        assert record.status == "cancelled"
        assert 1 <= record.progress["done"] < record.progress["total"]
    finally:
        manager.shutdown()
