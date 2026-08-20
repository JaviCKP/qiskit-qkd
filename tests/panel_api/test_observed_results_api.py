from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from panel.api.app import create_app
from qiskit_qkd.config import EveConfig, Scenario


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(store_dir=tmp_path, use_processes=False))


def _contains_internal_eve(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            isinstance(key, str)
            and (
                key == "eavesdropper"
                or key == "tags"
                or key.startswith("eve_")
            )
            or _contains_internal_eve(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_internal_eve(item) for item in value)
    return False


def test_run_result_is_observed_and_diagnostics_are_explicit(tmp_path: Path) -> None:
    scenario = Scenario(
        pulses=32,
        clock_rate_hz=1_000_000.0,
        seed=19,
        eavesdropper=EveConfig(
            kind="intercept_resend",
            intercept_probability=1.0,
        ),
        event_sample_size=8,
    )
    client = _client(tmp_path)

    created = client.post("/api/runs", json={"scenario": scenario.to_dict()})
    assert created.status_code == 200
    job_id = created.json()["job_id"]

    status = client.get(f"/api/runs/{job_id}")
    assert status.status_code == 200
    assert "result_internal" not in status.json()
    assert "result_internal" not in status.json().get("result_summary", {})

    observed_response = client.get(f"/api/runs/{job_id}/result")
    assert observed_response.status_code == 200
    observed = observed_response.json()
    assert not _contains_internal_eve(observed)
    assert "authoritative_metrics" in observed
    assert "qber_defined" in observed["authoritative_metrics"]

    diagnostics_response = client.get(f"/api/runs/{job_id}/diagnostics")
    assert diagnostics_response.status_code == 200
    diagnostics = diagnostics_response.json()
    assert _contains_internal_eve(diagnostics)

    opted_in = client.get(
        f"/api/runs/{job_id}/result",
        params={"include_diagnostics": "true"},
    )
    assert opted_in.status_code == 200
    assert not _contains_internal_eve(opted_in.json()["observed"])
    assert _contains_internal_eve(opted_in.json()["diagnostics"])
