from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from panel.api.app import create_app
from panel.api.limits import DEFAULT_OPERATIONAL_LIMITS, OperationalLimits
from qiskit_qkd.config import ChannelConfig, Scenario


def _client(
    tmp_path: Path,
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> TestClient:
    return TestClient(
        create_app(
            store_dir=tmp_path,
            use_processes=False,
            operational_limits=limits,
        ),
    )


def _scenario(**updates: object) -> dict[str, object]:
    payload = Scenario(pulses=20, clock_rate_hz=1_000_000.0, seed=17).to_dict()
    payload.update(updates)
    return payload


def test_run_returns_a_pre_execution_upper_bound_cost(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/runs",
        json={"scenario": _scenario(event_sample_size=7)},
    )

    assert response.status_code == 200
    estimate = response.json()["cost_estimate"]
    assert estimate == {
        "estimate_kind": "upper_bound",
        "evaluations": 1,
        "pulses_per_evaluation": 20,
        "total_pulse_events": 20,
        "estimated_max_circuits": 20,
        "shots_per_circuit": 1,
        "estimated_max_shots": 20,
        "estimated_stored_events": 7,
        "backend": "statevector",
        "full_event_log": False,
        "warnings": [],
    }


def test_estimate_endpoints_do_not_submit_jobs(tmp_path: Path) -> None:
    app = create_app(store_dir=tmp_path, use_processes=False)
    client = TestClient(app)

    run = client.post("/api/runs/estimate", json={"scenario": _scenario()})
    sweep = client.post(
        "/api/sweeps/estimate",
        json={
            "scenario": _scenario(),
            "axis": {"target": "scenario.pulses", "values": [10, 20]},
            "repeats": 2,
        },
    )

    assert run.status_code == 200
    assert run.json()["total_pulse_events"] == 20
    assert sweep.status_code == 200
    assert sweep.json()["total_pulse_events"] == 60
    assert app.state.job_manager._records == {}


def test_run_rejects_pulses_above_the_configured_limit(tmp_path: Path) -> None:
    limits = replace(DEFAULT_OPERATIONAL_LIMITS, max_run_pulses=20)

    response = _client(tmp_path, limits=limits).post(
        "/api/runs",
        json={"scenario": _scenario(pulses=21)},
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "RUN_PULSE_LIMIT_EXCEEDED"
    assert issue["loc"] == "scenario.pulses"
    assert issue["context"]["max_run_pulses"] == 20
    assert issue["suggestion"]


def test_full_event_log_is_rejected_before_a_large_run_is_submitted(
    tmp_path: Path,
) -> None:
    limits = replace(DEFAULT_OPERATIONAL_LIMITS, max_full_event_log_events=20)

    response = _client(tmp_path, limits=limits).post(
        "/api/runs",
        json={"scenario": _scenario(pulses=21, store_full_event_log=True)},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "FULL_EVENT_LOG_LIMIT_EXCEEDED"


def test_event_sample_and_configuration_lists_are_bounded(tmp_path: Path) -> None:
    client = _client(tmp_path)

    event_sample = client.post(
        "/api/runs",
        json={
            "scenario": _scenario(
                event_sample_size=DEFAULT_OPERATIONAL_LIMITS.max_event_sample_size
                + 1,
            ),
        },
    )
    assert event_sample.status_code == 422
    assert event_sample.json()["errors"][0]["code"] == (
        "EVENT_SAMPLE_LIMIT_EXCEEDED"
    )

    count = DEFAULT_OPERATIONAL_LIMITS.max_decoy_intensities + 1
    decoys = [
        {
            "name": f"d{index}",
            "mean_photon_number": 0.1,
            "selection_probability": 1.0 / count,
        }
        for index in range(count)
    ]
    configuration = client.post(
        "/api/runs",
        json={
            "scenario": _scenario(
                source={
                    "kind": "decoy_weak_coherent",
                    "mean_photon_number": None,
                    "decoy_intensities": decoys,
                },
            ),
        },
    )
    assert configuration.status_code == 422
    assert configuration.json()["errors"][0]["code"] == (
        "DECOY_INTENSITY_LIMIT_EXCEEDED"
    )


def test_api_rejects_operationally_excessive_photon_intensity(
    tmp_path: Path,
) -> None:
    response = _client(tmp_path).post(
        "/api/runs",
        json={
            "scenario": _scenario(
                source={
                    "kind": "weak_coherent",
                    "mean_photon_number": (
                        DEFAULT_OPERATIONAL_LIMITS.max_mean_photon_number + 0.1
                    ),
                    "preparation_error_probability": 0.0,
                    "emission_probability": 1.0,
                    "decoy_intensities": [],
                },
            ),
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == (
        "MEAN_PHOTON_NUMBER_LIMIT_EXCEEDED"
    )


def test_sweep_rejects_total_pulse_product_even_with_few_evaluations(
    tmp_path: Path,
) -> None:
    limits = replace(DEFAULT_OPERATIONAL_LIMITS, max_total_pulse_events=100)

    response = _client(tmp_path, limits=limits).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(pulses=40),
            "axis": {
                "target": "detector.efficiency",
                "values": [0.5, 0.6, 0.7],
            },
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "TOTAL_PULSE_EVENT_LIMIT_EXCEEDED"
    assert issue["value"] == 120
    assert issue["context"]["evaluations"] == 3


def test_sweep_accepts_the_exact_cost_boundary_and_returns_estimate(
    tmp_path: Path,
) -> None:
    limits = replace(DEFAULT_OPERATIONAL_LIMITS, max_total_pulse_events=100)

    response = _client(tmp_path, limits=limits).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(pulses=10),
            "axis": {"target": "scenario.pulses", "values": [20, 30]},
            "repeats": 2,
        },
    )

    assert response.status_code == 200
    estimate = response.json()["cost_estimate"]
    assert estimate["evaluations"] == 4
    assert estimate["pulses_per_evaluation"] == 30
    assert estimate["total_pulse_events"] == 100
    assert estimate["estimated_max_circuits"] == 100


def test_maximum_sweep_compact_payload_fits_operational_storage_limits(
    tmp_path: Path,
) -> None:
    points = DEFAULT_OPERATIONAL_LIMITS.max_sweep_evaluations
    response = _client(tmp_path).post(
        "/api/sweeps/estimate",
        json={
            "scenario": _scenario(
                pulses=1,
                channel=ChannelConfig(kind="fiber").to_dict(),
            ),
            "axis": {
                "target": "channel.distance_km",
                "values": {"start": 0.0, "stop": 100.0, "steps": points},
            },
        },
    )

    assert response.status_code == 200
    estimate = response.json()
    assert estimate["evaluations"] == points
    assert (
        estimate["estimated_payload_bytes"]
        <= DEFAULT_OPERATIONAL_LIMITS.max_sweep_payload_bytes
    )
    assert (
        estimate["estimated_artifact_bytes"]
        <= DEFAULT_OPERATIONAL_LIMITS.max_sweep_artifact_bytes
    )


def test_sweep_byte_budget_rejects_before_job_submission(tmp_path: Path) -> None:
    limits = replace(
        DEFAULT_OPERATIONAL_LIMITS,
        max_sweep_payload_bytes=70_000,
        max_sweep_artifact_bytes=80_000,
    )
    app = create_app(
        store_dir=tmp_path,
        use_processes=False,
        operational_limits=limits,
    )
    response = TestClient(app).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(
                pulses=1,
                channel=ChannelConfig(kind="fiber").to_dict(),
            ),
            "axis": {"target": "channel.distance_km", "values": [0.0, 1.0]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == (
        "SWEEP_PAYLOAD_BYTE_LIMIT_EXCEEDED"
    )
    assert app.state.job_manager._records == {}


def test_scenario_inspection_consolidates_validation_characterization_and_cost(
    tmp_path: Path,
) -> None:
    scenario = _scenario(event_sample_size=3)

    response = _client(tmp_path).post(
        "/api/scenarios/inspect",
        json={"scenario": scenario},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["digest"] == Scenario.from_dict(scenario).digest()
    assert payload["resolution_time_s"] == 0.0
    assert payload["effective_scenario"]["pulses"] == 20
    assert set(payload["characterizations"]) == {
        "source",
        "channel",
        "detector",
        "timing",
    }
    assert payload["cost_estimate"]["total_pulse_events"] == 20


def test_openapi_exposes_named_request_response_and_cost_models(
    tmp_path: Path,
) -> None:
    schema = _client(tmp_path).get("/openapi.json").json()

    assert "/api/scenarios/inspect" in schema["paths"]
    component_names = set(schema["components"]["schemas"])
    assert {
        "RunRequest",
        "RunCreatedResponse",
        "SweepRequest",
        "SweepCreatedResponse",
        "ScenarioInspectRequest",
        "ScenarioInspectionResponse",
        "CostEstimateResponse",
    } <= component_names


def test_non_finite_known_numbers_have_a_stable_422_shape(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/runs",
        content=(
            '{"scenario":{"pulses":20,"clock_rate_hz":NaN,"seed":17}}'
        ),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["loc"] == "clock_rate_hz"
    assert "finite" in issue["msg"].lower()
