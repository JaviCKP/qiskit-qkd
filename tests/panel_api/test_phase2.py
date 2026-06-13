from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from panel.api.app import create_app
from qiskit_qkd.config import Scenario


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
        field["key"]
        for section in payload["sections"]
        for field in section["fields"]
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


def test_run_job_executes_small_bb84_scenario(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/api/runs",
        json={"scenario": _scenario_payload(event_sample_size=5), "label": "small"},
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


def test_sweep_job_returns_rows_and_summary(tmp_path: Path) -> None:
    client = _client(tmp_path)

    created = client.post(
        "/api/sweeps",
        json={
            "scenario": _scenario_payload(),
            "axis": {
                "target": "channel.distance_km",
                "values": {"start": 0.0, "stop": 10.0, "steps": 3},
            },
            "repeats": 2,
        },
    )

    assert created.status_code == 200
    payload = client.get(f"/api/sweeps/{created.json()['job_id']}").json()
    assert payload["status"] == "done"
    assert len(payload["result"]["rows"]) == 6
    assert len(payload["result"]["summary"]) == 3


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
        json={"name": "fibra", "scenario": scenario, "tags": ["tfg"]},
    )
    assert created.status_code == 200
    experiment_id = created.json()["experiment"]["id"]

    listed = client.get("/api/experiments")
    assert listed.json()["experiments"][0]["id"] == experiment_id

    fetched = client.get(f"/api/experiments/{experiment_id}")
    assert fetched.json()["experiment"]["name"] == "fibra"

    deleted = client.delete(f"/api/experiments/{experiment_id}")
    assert deleted.status_code == 200
    assert client.get("/api/experiments").json()["experiments"] == []


def test_presets_returns_four_canonical_scenarios(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/presets")

    assert response.status_code == 200
    presets = response.json()["presets"]
    assert len(presets) == 4
    assert {preset["name"] for preset in presets} == {
        "Fibra metropolitana",
        "Satélite LEO",
        "PNS sobre decoy débil",
        "E91 con scintillation",
    }
