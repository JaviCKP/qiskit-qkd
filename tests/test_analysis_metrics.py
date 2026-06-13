from __future__ import annotations

import pytest

from qiskit_qkd import Metrics, Scenario, SimulationResult
from qiskit_qkd.analysis import (
    add_derived_metrics,
    metric_rows_from_results,
    secure_distance_limit,
    summarize_metric_rows,
)


def test_add_derived_metrics_enriches_rows_without_mutating_input() -> None:
    row = {
        "distance_km": 25.0,
        "pulses": 100,
        "emitted": 90,
        "transmitted": 80,
        "detected": 40,
        "sifted": 20,
        "errors": 2,
        "qber": 0.10,
        "secret_key_rate_bps": 12.0,
        "timing_discards": 5,
        "chsh_s": 2.42,
        "abort": False,
    }

    enriched = add_derived_metrics([row], qber_abort_threshold=0.11)[0]

    assert "sifted_fraction" not in row
    assert enriched["detected_fraction"] == 0.40
    assert enriched["transmission_fraction"] == pytest.approx(80 / 90)
    assert enriched["sifted_fraction"] == 0.50
    assert enriched["error_fraction"] == 0.10
    assert enriched["timing_discard_fraction"] == pytest.approx(5 / 80)
    assert enriched["qber_margin"] == pytest.approx(0.01)
    assert enriched["chsh_margin"] == pytest.approx(0.42)
    assert enriched["secure"] is True


def test_metric_rows_from_results_flattens_metrics_and_classical_diagnostics() -> None:
    scenario = Scenario(pulses=100, clock_rate_hz=1_000.0, seed=7)
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(
            pulses=100,
            emitted=100,
            transmitted=90,
            detected=80,
            sifted=40,
            errors=2,
            qber=0.05,
            gain=0.8,
            secret_key_rate_bps=120.0,
        ),
        classical={
            "corrected_key_length": 30,
            "final_key_length": 24,
            "leak_ec": 6,
        },
    )

    rows = metric_rows_from_results(
        {"baseline": result},
        qber_abort_threshold=0.11,
    )

    assert rows == [
        {
            "label": "baseline",
            "seed": 7,
            "protocol": "bb84",
            "channel_kind": "ideal",
            "source_kind": "ideal_single_photon",
            "pulses": 100,
            "emitted": 100,
            "transmitted": 90,
            "detected": 80,
            "sifted": 40,
            "errors": 2,
            "qber": 0.05,
            "loss_db": 0.0,
            "gain": 0.8,
            "raw_detection_rate_hz": 0.0,
            "sifted_key_rate_bps": 0.0,
            "secret_key_rate_bps": 120.0,
            "abort": False,
            "timing_discards": 0,
            "dead_time_discards": 0,
            "afterpulse_clicks": 0,
            "eve_intercepted_fraction": 0.0,
            "eve_information_estimate": 0.0,
            "chsh_s": None,
            "corrected_key_length": 30,
            "final_key_length": 24,
            "leak_ec": 6,
            "privacy_efficiency": 0.8,
            "detected_fraction": 0.8,
            "emission_fraction": 1.0,
            "transmission_fraction": 0.9,
            "sifted_fraction": 0.5,
            "error_fraction": 0.05,
            "timing_discard_fraction": 0.0,
            "qber_margin": pytest.approx(0.06),
            "secure": True,
        },
    ]


def test_summarize_metric_rows_aggregates_repeats_and_abort_fraction() -> None:
    rows = [
        {
            "distance_km": 0.0,
            "repeat": 0,
            "qber": 0.10,
            "secret_key_rate_bps": 100.0,
            "abort": False,
        },
        {
            "distance_km": 0.0,
            "repeat": 1,
            "qber": 0.30,
            "secret_key_rate_bps": 80.0,
            "abort": True,
        },
        {
            "distance_km": 50.0,
            "repeat": 0,
            "qber": 0.40,
            "secret_key_rate_bps": 0.0,
            "abort": True,
        },
    ]

    summary = summarize_metric_rows(
        rows,
        group_by=("distance_km",),
        metrics=("qber", "secret_key_rate_bps"),
    )

    assert summary[0]["distance_km"] == 0.0
    assert summary[0]["samples"] == 2
    assert summary[0]["qber_mean"] == pytest.approx(0.20)
    assert summary[0]["qber_std"] == pytest.approx(0.10)
    assert summary[0]["qber_min"] == 0.10
    assert summary[0]["qber_max"] == 0.30
    assert summary[0]["secret_key_rate_bps_mean"] == pytest.approx(90.0)
    assert summary[0]["abort_fraction"] == 0.5

    assert summary[1]["distance_km"] == 50.0
    assert summary[1]["samples"] == 1
    assert summary[1]["qber_std"] == 0.0
    assert summary[1]["abort_fraction"] == 1.0


def test_secure_distance_limit_returns_last_positive_non_aborted_rate() -> None:
    rows = [
        {"distance_km": 0.0, "secret_key_rate_bps": 10.0, "abort": False},
        {"distance_km": 25.0, "secret_key_rate_bps": 3.0, "abort": False},
        {"distance_km": 50.0, "secret_key_rate_bps": 1.0, "abort": True},
        {"distance_km": 75.0, "secret_key_rate_bps": 0.0, "abort": False},
    ]

    assert secure_distance_limit(rows) == 25.0
