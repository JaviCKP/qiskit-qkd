from __future__ import annotations

from qiskit_qkd import (
    EveConfig,
    Event,
    Metrics,
    PostProcessingConfig,
    Scenario,
    SimulationResult,
    extract_authoritative_metrics,
    observed_metric_rows_from_results,
)


def _scenario(*, threshold: float | None = 0.11, sample_size: int = 1) -> Scenario:
    return Scenario(
        pulses=10,
        clock_rate_hz=1_000.0,
        seed=7,
        post_processing=PostProcessingConfig(qber_abort_threshold=threshold),
        eavesdropper=EveConfig(kind="intercept_resend", intercept_probability=1.0),
        event_sample_size=sample_size,
    )


def test_authoritative_metrics_marks_qber_undefined() -> None:
    result = SimulationResult(
        scenario=_scenario(sample_size=0),
        metrics=Metrics(pulses=10),
    )

    extracted = extract_authoritative_metrics(result)

    assert extracted["qber_defined"] is False
    assert extracted["qber_value"] is None
    assert extracted["qber"] is None
    assert extracted["threshold_decision"] is None
    assert extracted["qber_evidence_origin"] == "unavailable"


def test_authoritative_metrics_reports_threshold_verification_and_rate() -> None:
    result = SimulationResult(
        scenario=_scenario(),
        metrics=Metrics(
            pulses=10,
            emitted=10,
            transmitted=10,
            detected=10,
            sifted=10,
            errors=2,
            secret_key_rate_bps=5.0,
        ),
        classical={"verification_status": "passed", "final_key_length": 4},
    )

    extracted = extract_authoritative_metrics(result)

    assert extracted["qber_defined"] is True
    assert extracted["qber_value"] == 0.2
    assert extracted["threshold_decision"] is True
    assert extracted["threshold_decision_origin"] == "metrics_legacy"
    assert extracted["verification_status"] == "not_performed"
    assert extracted["rate_status"] == "inconsistent_with_key_status"
    assert extracted["rate_applicable"] is False


def test_observed_view_excludes_eve_but_internal_diagnostics_keeps_it() -> None:
    event = Event(
        index=0,
        time_s=0.0,
        eve_action="intercept_resend",
        eve_basis="X",
        eve_detectable=True,
        tags={"eve_measured_bit": 1, "source": "unit"},
    )
    result = SimulationResult(
        scenario=_scenario(),
        metrics=Metrics(
            pulses=10,
            eve_intercepted_fraction=0.5,
            eve_information_estimate=0.25,
        ),
        event_sample=(event,),
    )

    observed = result.to_observed_dict()
    diagnostics = result.to_internal_diagnostics_dict()

    assert "eavesdropper" not in observed["scenario"]
    assert not any(key.startswith("eve_") for key in observed["metrics"])
    assert not any(key.startswith("eve_") for key in observed["event_sample"][0])
    assert "eve_measured_bit" not in observed["event_sample"][0]["tags"]
    assert diagnostics["metrics"]["eve_intercepted_fraction"] == 0.5
    assert diagnostics["event_sample"][0]["eve_action"] == "intercept_resend"


def test_observed_metric_rows_exclude_eve_legacy_columns() -> None:
    result = SimulationResult(
        scenario=_scenario(sample_size=0),
        metrics=Metrics(pulses=10, eve_information_estimate=0.5),
    )

    row = observed_metric_rows_from_results([result])[0]

    assert not any(key.startswith("eve_") for key in row)
