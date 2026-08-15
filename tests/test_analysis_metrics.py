from __future__ import annotations

import pytest

from qiskit_qkd import Metrics, PostProcessingConfig, Scenario, SimulationResult
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
    assert enriched["key_estimate_available"] is False
    assert enriched["secure"] is False
    assert enriched["secure_is_legacy"] is True


def test_add_derived_metrics_only_marks_an_explicit_key_estimate_available() -> None:
    rows = [
        {
            "secret_key_rate_bps": 12.0,
            "abort": False,
            "key_status": "estimated_key_available",
        },
        {
            "secret_key_rate_bps": 12.0,
            "abort": False,
            "key_status": "no_key_verification_failed",
        },
    ]

    enriched = add_derived_metrics(rows)

    assert enriched[0]["key_estimate_available"] is True
    assert enriched[1]["key_estimate_available"] is False
    assert all(row["secure"] is False for row in enriched)
    assert all(row["secure_is_legacy"] is True for row in enriched)


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

    assert len(rows) == 1
    row = rows[0]
    assert row["label"] == "baseline"
    assert row["seed"] == 7
    assert row["protocol"] == "bb84"
    assert row["corrected_key_length"] == 30
    assert row["final_key_length"] == 24
    assert row["privacy_efficiency"] == 0.8
    assert row["detected_fraction"] == 0.8
    assert row["error_fraction"] == 0.05
    assert row["qber_margin"] == pytest.approx(0.06)
    assert row["data_status"] == "available"
    assert row["qber_defined"] is True
    assert row["qber_method"] == "full_sifted_key_diagnostic"
    assert row["sample_size"] == 40
    assert row["key_status"] == "estimated_key_available"
    assert row["key_estimate_available"] is True
    assert "reason_codes" not in row
    assert row["secure"] is False
    assert row["secure_is_legacy"] is True


def test_metric_rows_use_null_authoritative_qber_when_no_sample_exists() -> None:
    result = SimulationResult(
        scenario=Scenario(pulses=10, clock_rate_hz=1_000.0, seed=71),
        metrics=Metrics(pulses=10, qber=0.0, abort=False),
    )

    row = metric_rows_from_results(
        [result],
        qber_abort_threshold=0.11,
    )[0]

    assert row["qber_defined"] is False
    assert row["qber"] is None
    assert row["legacy_qber"] == 0.0
    assert row["qber_margin"] is None
    assert row["legacy_abort"] is False
    assert row["abort"] is False
    assert row["abort_is_legacy"] is True


def test_metric_rows_prefer_classical_qber_evidence_over_legacy_metric() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=1_000.0,
        seed=72,
        post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
    )
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(
            pulses=100,
            emitted=100,
            transmitted=100,
            detected=100,
            sifted=100,
            errors=10,
            qber=0.10,
            abort=False,
        ),
        classical={
            "qber_sample_size": 10,
            "estimated_qber": 0.20,
            "qber_method": "revealed_sample",
            "threshold": 0.11,
            "threshold_exceeded": True,
            "threshold_decision_source": "classical_estimate",
            "abort": True,
            "final_key_length": 0,
            "verification_status": "not_performed",
        },
    )

    row = metric_rows_from_results(
        [result],
        qber_abort_threshold=0.11,
    )[0]

    assert row["qber"] == 0.20
    assert row["qber_value"] == 0.20
    assert row["legacy_qber"] == 0.10
    assert row["qber_margin"] == pytest.approx(-0.09)
    assert row["threshold_exceeded"] is True
    assert row["legacy_abort"] is False


def test_summarize_metric_rows_aggregates_repeats_and_abort_fraction() -> None:
    rows = [
        {
            "distance_km": 0.0,
            "repeat": 0,
            "qber": 0.10,
            "secret_key_rate_bps": 100.0,
            "abort": False,
            "threshold_exceeded": False,
        },
        {
            "distance_km": 0.0,
            "repeat": 1,
            "qber": 0.30,
            "secret_key_rate_bps": 80.0,
            "abort": True,
            "threshold_exceeded": True,
        },
        {
            "distance_km": 50.0,
            "repeat": 0,
            "qber": 0.40,
            "secret_key_rate_bps": 0.0,
            "abort": True,
            "threshold_exceeded": True,
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
    assert summary[0]["qber_finite_count"] == 2
    assert summary[0]["secret_key_rate_bps_mean"] == pytest.approx(90.0)
    assert summary[0]["secret_key_rate_bps_finite_count"] == 2
    assert summary[0]["abort_fraction"] == 0.5
    assert summary[0]["abort_fraction_is_legacy"] is True
    assert summary[0]["legacy_abort_fraction"] == 0.5
    assert summary[0]["threshold_decision_count"] == 2
    assert summary[0]["threshold_decision_fraction"] == 0.5

    assert summary[1]["distance_km"] == 50.0
    assert summary[1]["samples"] == 1
    assert summary[1]["qber_mean"] == 0.40
    assert summary[1]["qber_min"] == 0.40
    assert summary[1]["qber_max"] == 0.40
    assert summary[1]["qber_finite_count"] == 1
    assert "qber_std" not in summary[1]
    assert "qber_p05" not in summary[1]
    assert "qber_p95" not in summary[1]
    assert summary[1]["abort_fraction"] == 1.0
    assert summary[1]["legacy_abort_fraction"] == 1.0
    assert summary[1]["threshold_decision_count"] == 1
    assert summary[1]["threshold_decision_fraction"] == 1.0


def test_secure_distance_limit_requires_consistent_assessed_key_estimate() -> None:
    rows = [
        {
            "distance_km": 0.0,
            "secret_key_rate_bps": 10.0,
            "key_status": "estimated_key_available",
            "rate_estimate_status": "available",
        },
        {
            "distance_km": 25.0,
            "secret_key_rate_bps": 3.0,
            "key_status": "estimated_key_available",
            "rate_estimate_status": "available",
        },
        {
            "distance_km": 50.0,
            "secret_key_rate_bps": 2.0,
            "key_status": "no_key_verification_failed",
            "rate_estimate_status": "inconsistent_with_key_status",
        },
        {
            "distance_km": 75.0,
            "secret_key_rate_bps": 1.0,
            "key_status": "no_key_threshold_exceeded",
            "rate_estimate_status": "available",
        },
        {
            "distance_km": 100.0,
            "secret_key_rate_bps": 1.0,
            "abort": False,
        },
    ]

    assert secure_distance_limit(rows) == 25.0


def test_secure_distance_limit_rejects_legacy_rate_abort_only_rows() -> None:
    rows = [
        {"distance_km": 25.0, "secret_key_rate_bps": 3.0, "abort": False},
        {"distance_km": 50.0, "secret_key_rate_bps": 1.0, "abort": False},
    ]

    assert secure_distance_limit(rows) is None


def test_summary_marks_legacy_secure_fraction_and_reports_key_estimates() -> None:
    rows = [
        {
            "group": "baseline",
            "secure": True,
            "key_estimate_available": True,
        },
        {
            "group": "baseline",
            "secure": False,
            "key_estimate_available": False,
        },
    ]

    summary = summarize_metric_rows(
        rows,
        group_by=("group",),
        metrics=(),
    )[0]

    assert summary["secure_fraction"] == 0.0
    assert summary["secure_fraction_is_legacy"] is True
    assert summary["legacy_secure_input_true_fraction"] == 0.5
    assert summary["key_estimate_available_fraction"] == 0.5


def test_summary_omits_dispersion_with_only_one_finite_metric_value() -> None:
    rows = [
        {"group": "baseline", "qber": 0.1},
        {"group": "baseline", "qber": None},
    ]

    summary = summarize_metric_rows(
        rows,
        group_by=("group",),
        metrics=("qber",),
    )[0]

    assert summary["samples"] == 2
    assert summary["qber_finite_count"] == 1
    assert summary["qber_mean"] == 0.1
    assert summary["qber_min"] == 0.1
    assert summary["qber_max"] == 0.1
    assert "qber_std" not in summary
    assert "qber_p05" not in summary
    assert "qber_p95" not in summary


def test_summary_reports_zero_finite_metric_values() -> None:
    summary = summarize_metric_rows(
        [
            {"group": "baseline", "qber": None},
            {"group": "baseline", "qber": float("nan")},
        ],
        group_by=("group",),
        metrics=("qber",),
    )[0]

    assert summary["samples"] == 2
    assert summary["qber_finite_count"] == 0
    assert "qber_mean" not in summary


def test_summary_reports_no_authoritative_threshold_decisions() -> None:
    summary = summarize_metric_rows(
        [
            {
                "group": "no-sample",
                "legacy_abort": False,
                "threshold_exceeded": None,
            },
            {
                "group": "no-sample",
                "legacy_abort": False,
                "threshold_exceeded": None,
            },
        ],
        group_by=("group",),
        metrics=(),
    )[0]

    assert summary["legacy_abort_count"] == 2
    assert summary["legacy_abort_fraction"] == 0.0
    assert summary["threshold_decision_count"] == 0
    assert summary["threshold_decision_fraction"] is None
