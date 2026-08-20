"""Regression tests for the evidence-aware unexpected experiments."""

from __future__ import annotations

from types import SimpleNamespace

from experiments import experimentos_inesperados as experiments


def _fake_result(*, qber_defined: bool, rate_status: str) -> SimpleNamespace:
    metrics = SimpleNamespace(
        pulses=10,
        emitted=10,
        transmitted=10,
        detected=0,
        sifted=0,
        errors=0,
        qber=0.0,
        gain=0.0,
        loss_db=0.0,
        sifted_key_rate_bps=0.0,
        secret_key_rate_bps=999.0,
        abort=False,
        timing_discards=2,
        dead_time_discards=3,
        afterpulse_clicks=4,
        eve_intercepted_fraction=0.25,
        eve_information_estimate=0.75,
    )
    assessment = {
        "qber_defined": qber_defined,
        "qber_value": None if not qber_defined else 0.125,
        "rate_estimate_status": rate_status,
        "rate_estimate_bps": 12.5 if rate_status == "available" else None,
        "verification_status": "not_performed",
        "threshold_exceeded": None,
        "key_status": "no_key_insufficient_data",
    }
    return SimpleNamespace(
        metrics=metrics,
        assessment=assessment,
        classical={"verification_status": "not_performed"},
        decoy={"security": {"secret_key_rate_bps": 3.0}},
        bell={"observed_chsh_s": None},
    )


def test_run_uses_assessment_when_legacy_metrics_are_misleading(monkeypatch):
    monkeypatch.setattr(
        experiments,
        "run_result",
        lambda scenario: _fake_result(qber_defined=False, rate_status="unavailable"),
    )

    summary = experiments.run(object())

    assert summary["qber_defined"] is False
    assert summary["qber"] is None
    assert summary["rate_estimate_status"] == "unavailable"
    assert summary["secret_bps"] is None
    assert summary["decoy_security"]["secret_key_rate_bps"] == 3.0
    assert summary["timing_discards"] == 2
    assert summary["dead_time_discards"] == 3


def test_run_preserves_defined_assessment_rate(monkeypatch):
    monkeypatch.setattr(
        experiments,
        "run_result",
        lambda scenario: _fake_result(qber_defined=True, rate_status="available"),
    )

    summary = experiments.run(object())

    assert summary["qber"] == 0.125
    assert summary["secret_bps"] == 12.5
    assert summary["verification_status"] == "not_performed"


def test_run_marks_threshold_abort_from_assessment(monkeypatch):
    result = _fake_result(qber_defined=True, rate_status="inconsistent_with_key_status")
    result.assessment["key_status"] = "no_key_threshold_exceeded"
    result.assessment["threshold_exceeded"] = True
    monkeypatch.setattr(experiments, "run_result", lambda scenario: result)

    assert experiments.run(object())["abort"] is True
