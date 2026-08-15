from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from panel.api.app import create_app
from panel.api.store import ExperimentStore, StoreValidationError
from qiskit_qkd.config import Scenario


def _experiment(**updates: object) -> dict[str, object]:
    scenario = Scenario(pulses=8, clock_rate_hz=1_000_000.0, seed=7)
    payload: dict[str, object] = {
        "name": "metro",
        "scenario": scenario.to_dict(),
        "digest": scenario.digest(),
        "tags": ["test"],
        "last_result": None,
        "curve_recipes": [],
    }
    payload.update(updates)
    return payload


def test_atomic_replace_keeps_previous_json_when_commit_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ExperimentStore(tmp_path)
    first = store.save(_experiment(id="e_atomic", name="before"))
    original = (tmp_path / "e_atomic.json").read_bytes()

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("simulated interrupted replace")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="interrupted"):
        store.save(_experiment(id="e_atomic", name="after"))

    assert (tmp_path / "e_atomic.json").read_bytes() == original
    assert store.get("e_atomic") == first
    assert list(tmp_path.glob(".*.tmp")) == []


@pytest.mark.parametrize(
    "experiment_id",
    ["../secret", "..\\secret", ".hidden", "bad.json", "a/b", "", " space"],
)
def test_experiment_ids_use_a_strict_allowlist(
    tmp_path: Path,
    experiment_id: str,
) -> None:
    store = ExperimentStore(tmp_path)

    with pytest.raises(StoreValidationError, match="identifier"):
        store.save(_experiment(id=experiment_id))
    with pytest.raises(StoreValidationError, match="identifier"):
        store.get(experiment_id)

    assert list(tmp_path.iterdir()) == []


def test_invalid_import_is_rejected_with_structured_422(tmp_path: Path) -> None:
    client = TestClient(create_app(store_dir=tmp_path, use_processes=False))
    payload = _experiment(digest="0" * 64)

    response = client.post("/api/experiments/import", json={"experiment": payload})

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "EXPERIMENT_DIGEST_MISMATCH"
    assert issue["loc"] == "experiment.digest"
    assert client.get("/api/experiments").json() == {"experiments": []}


def test_deeply_nested_import_is_rejected_with_structured_422(
    tmp_path: Path,
) -> None:
    client = TestClient(create_app(store_dir=tmp_path, use_processes=False))
    nested: dict[str, object] = {}
    for _ in range(140):
        nested = {"child": nested}

    response = client.post(
        "/api/experiments/import",
        json={"experiment": _experiment(provenance=nested)},
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "EXPERIMENT_JSON_INVALID"
    assert "nesting depth" in issue["msg"]


def test_imported_provenance_claims_are_marked_unverified(tmp_path: Path) -> None:
    client = TestClient(create_app(store_dir=tmp_path, use_processes=False))
    payload = _experiment(
        provenance={"commit": "claimed-top-level"},
        last_result={
            "metrics": {"detected": 1},
            "provenance": {"backend": "claimed-backend", "commit": "claimed"},
        },
    )

    response = client.post("/api/experiments/import", json={"experiment": payload})

    assert response.status_code == 200
    experiment = response.json()["experiment"]
    assert experiment["provenance"] == {
        "claims_verified": False,
        "commit": "claimed-top-level",
        "verification_status": "unverified_import",
    }
    assert experiment["last_result"]["provenance"] == {
        "backend": "claimed-backend",
        "claims_verified": False,
        "commit": "claimed",
        "verification_status": "unverified_import",
    }


def test_experiment_reads_reject_symlinks_outside_store(tmp_path: Path) -> None:
    root = tmp_path / "store"
    outside = tmp_path / "outside"
    store = ExperimentStore(root)
    outside_store = ExperimentStore(outside)
    outside_store.save(_experiment(id="e_link", name="outside secret"))
    link = root / "e_link.json"
    try:
        link.symlink_to(outside / "e_link.json")
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable in this environment: {exc}")

    assert store.get("e_link") is None
    assert store.list() == []
    assert store.list_summaries() == ([], 0)


def test_experiment_read_rejects_descriptor_path_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ExperimentStore(tmp_path)
    store.save(_experiment(id="e_raced"))
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"replacement")
    descriptor = os.open(replacement, os.O_RDONLY)
    try:
        replacement_stat = os.fstat(descriptor)
    finally:
        os.close(descriptor)

    monkeypatch.setattr(os, "fstat", lambda _descriptor: replacement_stat)

    assert store.get("e_raced") is None


def test_corrupt_file_is_skipped_without_breaking_other_experiments(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = ExperimentStore(tmp_path)
    valid = store.save(_experiment(id="e_valid"))
    (tmp_path / "e_corrupt.json").write_text("{not-json", encoding="utf-8")

    listed = store.list()

    assert listed == [valid]
    assert store.get("e_corrupt") is None
    assert "e_corrupt.json" in caplog.text
    assert (tmp_path / "e_corrupt.json").read_text(encoding="utf-8") == "{not-json"


def test_nearby_concurrent_updates_never_expose_torn_json(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    first = store.save(_experiment(id="e_shared", name="initial"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        saved = list(
            executor.map(
                lambda index: store.save(
                    _experiment(id="e_shared", name=f"version-{index}"),
                ),
                range(32),
            ),
        )

    raw = json.loads((tmp_path / "e_shared.json").read_text(encoding="utf-8"))
    assert raw["name"] in {item["name"] for item in saved}
    assert raw["created_at"] == first["created_at"]
    assert datetime.fromisoformat(raw["updated_at"]) >= datetime.fromisoformat(
        raw["created_at"],
    )
    assert list(tmp_path.glob(".*.tmp")) == []


def test_store_rejects_non_json_values_and_oversized_lists(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path, max_tags=2)

    with pytest.raises(StoreValidationError, match="finite JSON"):
        store.save(_experiment(last_result={"qber": float("nan")}))
    with pytest.raises(StoreValidationError, match="at most 2"):
        store.save(_experiment(tags=["one", "two", "three"]))


def test_legacy_experiments_gain_additive_workspace_defaults(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)

    saved = store.save(_experiment())

    assert saved["schema_version"] == 1
    assert saved["runs"] == []
    assert saved["curves"] == []
    assert saved["provenance"] == {}


def test_workspace_history_is_validated_and_round_trips(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path, max_runs=2, max_curves=2)
    run = {"job_id": "run-1", "digest": _experiment()["digest"]}
    curve = {"job_id": "sweep-1", "metric": "qber"}

    saved = store.save(
        _experiment(
            schema_version=2,
            runs=[run],
            curves=[curve],
            provenance={"created_by": "qkd-panel"},
        ),
    )

    assert saved["schema_version"] == 2
    assert saved["runs"] == [run]
    assert saved["curves"] == [curve]
    assert saved["provenance"] == {"created_by": "qkd-panel"}

    with pytest.raises(StoreValidationError, match="at most 2"):
        store.save(_experiment(runs=[run, run, run]))


def test_builtin_presets_are_not_materialized_as_user_experiments(
    tmp_path: Path,
) -> None:
    app = create_app(store_dir=tmp_path, use_processes=False)

    with TestClient(app) as client:
        assert len(client.get("/api/presets").json()["presets"]) == 7
        assert client.get("/api/experiments").json() == {"experiments": []}

    assert list(tmp_path.glob("*.json")) == []


def test_v2_records_are_typed_and_last_result_is_not_duplicated_on_disk(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path)
    result = {"metrics": {"qber": 0.1}, "event_sample": [{"index": 0}]}
    saved = store.save(
        _experiment(
            schema_version=2,
            runs=[{"job_id": "run-1", "result": result}],
            last_result=result,
        ),
    )

    raw = json.loads((tmp_path / f"{saved['id']}.json").read_text(encoding="utf-8"))
    assert "last_result" not in raw
    assert store.get(saved["id"])["last_result"] == result

    with pytest.raises(StoreValidationError, match="must include"):
        store.save(_experiment(schema_version=2, runs=[{"digest": "missing id"}]))


def test_v2_experiment_explicitly_migrates_embedded_v1_scenario(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    scenario = Scenario(pulses=8, clock_rate_hz=1_000_000.0, seed=7)
    saved = store.save(
        _experiment(
            schema_version=2,
            scenario=scenario.to_dict(schema_version=1),
            digest=scenario.digest(),
        ),
    )

    assert saved["schema_version"] == 2
    assert saved["scenario"]["schema_version"] == 2
    assert saved["digest"] == scenario.digest()


def test_explicit_experiment_migration_updates_nested_scenario_without_mutation(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path)
    source = _experiment(
        schema_version=1,
        scenario=Scenario(
            pulses=8,
            clock_rate_hz=1_000_000.0,
            seed=7,
        ).to_dict(schema_version=1),
    )
    migrated = store.migrate_v1_to_v2(source)

    assert source["schema_version"] == 1
    assert source["scenario"]["schema_version"] == 1
    assert migrated["schema_version"] == 2
    assert migrated["scenario"]["schema_version"] == 2


def test_unknown_experiment_version_exposes_found_version_and_suggestion(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path)
    payload = _experiment(schema_version=99)

    with pytest.raises(StoreValidationError) as caught:
        store.save(payload)

    issue = caught.value.errors[0]
    assert issue["code"] == "EXPERIMENT_SCHEMA_VERSION_UNSUPPORTED"
    assert issue["context"]["found_version"] == 99
    assert "schema_version 2" in issue["suggestion"]


def test_summary_pagination_excludes_heavy_fields_and_enforces_quota(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(
        tmp_path,
        max_payload_bytes=100_000,
        max_total_bytes=100_000,
    )
    for index in range(3):
        store.save(_experiment(id=f"e_{index}", name=f"e-{index}"))

    summaries, total = store.list_summaries(limit=1, offset=1)

    assert total == 3
    assert len(summaries) == 1
    assert summaries[0]["name"] == "e-1"
    assert "scenario" not in summaries[0]
    assert "last_result" not in summaries[0]
    assert "runs" not in summaries[0]

    with pytest.raises(StoreValidationError, match="quota"):
        store.save(_experiment(id="e_too_big", last_result={"text": "x" * 90_000}))


def test_summary_listing_skips_digest_corruption_without_loading_results(
    tmp_path: Path,
) -> None:
    store = ExperimentStore(tmp_path)
    saved = store.save(_experiment(id="e_corrupt_summary"))
    path = tmp_path / f"{saved['id']}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["digest"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    summaries, total = store.list_summaries()

    assert summaries == []
    assert total == 0
