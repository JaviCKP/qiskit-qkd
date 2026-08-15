from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from panel.api.app import create_app
from qiskit_qkd.analysis import (
    expand_compact_sweep_rows,
    expand_compact_sweep_summary,
)
from qiskit_qkd.config import ChannelConfig, Scenario


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(store_dir=tmp_path, use_processes=False))


def _scenario_payload(**updates: object) -> dict[str, object]:
    payload = Scenario(pulses=32, clock_rate_hz=1_000_000.0, seed=123).to_dict()
    payload.update(updates)
    return payload


def test_catalog_exposes_parameters_and_metrics(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/catalog")

    assert response.status_code == 200
    payload = response.json()
    keys = {
        field["key"] for section in payload["sections"] for field in section["fields"]
    }
    metrics = {metric["key"] for metric in payload["metrics"]}
    assert "channel.distance_km" in keys
    assert "scenario.pulses" in keys
    assert "qber" in metrics
    assert "secret_key_rate_bps" in metrics


def test_scenario_validation_maps_library_errors_to_field_paths(
    tmp_path: Path,
) -> None:
    scenario = _scenario_payload()
    scenario["channel"]["distance_km"] = -1.0

    response = _client(tmp_path).post(
        "/api/scenarios/validate",
        json={"scenario": scenario},
    )

    assert response.status_code == 422
    assert response.json() == {
        "errors": [
            {
                "loc": "channel.distance_km",
                "msg": "distance_km must be greater than or equal to 0",
            },
        ],
    }


def test_scenario_validation_reports_all_missing_required_fields(
    tmp_path: Path,
) -> None:
    response = _client(tmp_path).post(
        "/api/scenarios/validate",
        json={"scenario": {}},
    )

    assert response.status_code == 422
    assert {error["loc"] for error in response.json()["errors"]} == {
        "pulses",
        "clock_rate_hz",
        "seed",
    }


def test_scenario_validation_maps_nested_missing_fields_to_422(
    tmp_path: Path,
) -> None:
    scenario = _scenario_payload()
    scenario["source"] = {
        "kind": "decoy_weak_coherent",
        "mean_photon_number": None,
        "decoy_intensities": [{}],
    }

    response = _client(tmp_path).post(
        "/api/scenarios/validate",
        json={"scenario": scenario},
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"loc": "name", "msg": "name is required"},
    ]


@pytest.mark.parametrize(
    "section",
    [
        "protocol",
        "source",
        "channel",
        "detector",
        "timing",
        "post_processing",
        "eavesdropper",
        "e91",
        "dynamic",
        "metadata",
    ],
)
def test_scenario_validation_rejects_non_object_sections_with_422(
    tmp_path: Path,
    section: str,
) -> None:
    scenario = _scenario_payload()
    scenario[section] = []

    response = _client(tmp_path).post(
        "/api/scenarios/validate",
        json={"scenario": scenario},
    )

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"loc": section, "msg": f"{section} must be an object"},
    ]


def test_run_job_executes_small_bb84_scenario(tmp_path: Path) -> None:
    client = _client(tmp_path)
    scenario_payload = _scenario_payload(event_sample_size=5)

    created = client.post(
        "/api/runs",
        json={"scenario": scenario_payload, "label": "small"},
    )

    assert created.status_code == 200
    job_id = created.json()["job_id"]
    status = client.get(f"/api/runs/{job_id}")
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "done"
    assert payload["progress"] == {"done": 1, "total": 1}
    assert payload["result_summary"]["metrics"]["pulses"] == 32
    assert payload["result_summary"]["event_sample_size"] <= 5
    provenance = payload["result_summary"]["provenance"]
    requested_digest = Scenario.from_dict(scenario_payload).digest()
    assert provenance["requested_scenario_digest"] == requested_digest
    assert (
        provenance["effective_scenario_digest"]
        == payload["result_summary"]["scenario_digest"]
    )
    assert provenance["resolution_time_s"] == 0.0


def test_run_job_preserves_an_explicit_full_event_log(tmp_path: Path) -> None:
    client = _client(tmp_path)
    scenario_payload = _scenario_payload(
        pulses=205,
        event_sample_size=1,
        store_full_event_log=True,
    )

    created = client.post("/api/runs", json={"scenario": scenario_payload})

    assert created.status_code == 200
    result = client.get(f"/api/runs/{created.json()['job_id']}/result")
    assert result.status_code == 200
    payload = result.json()
    assert payload["aggregated"] is False
    assert payload["scenario"]["store_full_event_log"] is True
    assert payload["scenario"]["event_sample_size"] == 1
    assert len(payload["event_sample"]) == 205


def test_job_routes_do_not_expose_records_of_another_kind(tmp_path: Path) -> None:
    client = _client(tmp_path)
    run = client.post(
        "/api/runs",
        json={"scenario": _scenario_payload(pulses=8)},
    )
    assert run.status_code == 200
    run_id = run.json()["job_id"]

    assert client.get(f"/api/sweeps/{run_id}").status_code == 404
    assert client.delete(f"/api/sweeps/{run_id}").json() == {"cancelled": False}

    sweep = client.post(
        "/api/sweeps",
        json={
            "scenario": _scenario_payload(pulses=8),
            "axis": {"target": "scenario.pulses", "values": [8, 9]},
        },
    )
    assert sweep.status_code == 200
    sweep_id = sweep.json()["job_id"]

    assert client.get(f"/api/runs/{sweep_id}").status_code == 404
    assert client.get(f"/api/runs/{sweep_id}/result").status_code == 404
    assert client.delete(f"/api/runs/{sweep_id}").json() == {"cancelled": False}


def test_sweep_job_returns_rows_and_summary(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/api/sweeps",
        json={
            "scenario": _scenario_payload(
                channel=ChannelConfig(kind="fiber").to_dict(),
            ),
            "axis": {
                "target": "channel.distance_km",
                "values": {"start": 0.0, "stop": 10.0, "steps": 3},
            },
            "repeats": 2,
        },
    )

    assert created.status_code == 200
    job_id = created.json()["job_id"]
    payload = client.get(f"/api/sweeps/{job_id}").json()
    assert payload["status"] == "done"
    assert "result" not in payload
    result = client.get(f"/api/sweeps/{job_id}/result").json()
    rows = expand_compact_sweep_rows(result)
    summary = expand_compact_sweep_summary(result["summary"])
    assert len(rows) == 6
    assert len(summary) == 3
    assert [row["seed"] for row in rows] == [
        123,
        124,
        123,
        124,
        123,
        124,
    ]
    assert all(
        row["provenance"]["resolution_time_s"] == 0.0
        for row in rows
    )


def test_sweep_job_resolves_dynamic_schedules_for_static_axis(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    scenario = _scenario_payload(
        channel=ChannelConfig(kind="fiber").to_dict(),
        dynamic={
            "parameter_schedules": [
                {
                    "target": "channel.distance_km",
                    "profile": {
                        "kind": "constant",
                        "start_s": 0.0,
                        "end_s": 1.0,
                        "value": 12.0,
                    },
                },
            ],
        },
    )

    created = client.post(
        "/api/sweeps",
        json={
            "scenario": scenario,
            "axis": {
                "target": "channel.distance_km",
                "values": {"start": 0.0, "stop": 10.0, "steps": 2},
            },
            "repeats": 1,
        },
    )

    assert created.status_code == 200
    job_id = created.json()["job_id"]
    payload = client.get(f"/api/sweeps/{job_id}").json()
    assert payload["status"] == "done"
    assert "error" not in payload
    assert "result" not in payload
    result = client.get(f"/api/sweeps/{job_id}/result").json()
    assert len(result["rows"]) == 2


def test_characterize_all_link_sections(tmp_path: Path) -> None:
    client = _client(tmp_path)
    scenario = _scenario_payload()

    for section in ("source", "channel", "detector", "timing"):
        response = client.post(
            f"/api/characterize/{section}",
            json={"scenario": scenario},
        )
        assert response.status_code == 200
        assert response.json()["section"] == section


def test_dynamics_preview_and_experiment_crud(tmp_path: Path) -> None:
    client = _client(tmp_path)
    scenario = _scenario_payload(
        dynamic={
            "parameter_schedules": [
                {
                    "target": "channel.distance_km",
                    "profile": {
                        "kind": "constant",
                        "start_s": 0.0,
                        "end_s": 1.0,
                        "value": 12.0,
                    },
                },
            ],
        },
    )

    preview = client.post(
        "/api/dynamics/preview",
        json={"scenario": scenario, "time_points_s": [0.0, 2.0]},
    )
    assert preview.status_code == 200
    assert preview.json()["rows"][0]["channel.distance_km"] == 12.0

    created = client.post(
        "/api/experiments",
        json={
            "name": "fibra",
            "scenario": scenario,
            "tags": ["tfg"],
            "schema_version": 2,
            "runs": [{"job_id": "run-1", "digest": "digest-1"}],
            "curves": [{"job_id": "sweep-1", "metric": "qber"}],
            "provenance": {"created_by": "qkd-panel"},
        },
    )
    assert created.status_code == 200
    experiment_id = created.json()["experiment"]["id"]

    listed = client.get("/api/experiments")
    assert listed.json()["experiments"][0]["id"] == experiment_id

    fetched = client.get(f"/api/experiments/{experiment_id}")
    assert fetched.json()["experiment"]["name"] == "fibra"
    assert len(fetched.json()["experiment"]["runs"]) == 1
    assert len(fetched.json()["experiment"]["curves"]) == 1

    renamed = client.patch(
        f"/api/experiments/{experiment_id}",
        json={"name": "fibra repetida"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["experiment"]["name"] == "fibra repetida"
    assert (
        renamed.json()["experiment"]["created_at"]
        == created.json()["experiment"]["created_at"]
    )
    assert len(renamed.json()["experiment"]["runs"]) == 1

    replaced = client.put(
        f"/api/experiments/{experiment_id}",
        json={
            "name": "fibra actualizada",
            "scenario": {**scenario, "seed": 456},
            "tags": ["tfg"],
            "schema_version": 2,
            "runs": [],
            "curves": [],
        },
    )
    assert replaced.status_code == 200
    assert replaced.json()["experiment"]["id"] == experiment_id
    assert (
        replaced.json()["experiment"]["created_at"]
        == created.json()["experiment"]["created_at"]
    )
    assert replaced.json()["experiment"]["scenario"]["seed"] == 456

    deleted = client.delete(f"/api/experiments/{experiment_id}")
    assert deleted.status_code == 200
    assert client.get("/api/experiments").json()["experiments"] == []


def test_presets_returns_canonical_scenarios(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/presets")

    assert response.status_code == 200
    presets = response.json()["presets"]
    assert len(presets) == 7
    assert {preset["name"] for preset in presets} == {
        "Fibra metropolitana (Ideal)",
        "Satélite LEO (Ideal)",
        "PNS sobre decoy débil",
        "E91 con scintillation",
        "Telecom Fibra 100 km (SNSPD Real)",
        "Free Space Urbano 1.5 km (SPAD Real)",
        "Enlace Submarino 30 m (Real)",
    }
