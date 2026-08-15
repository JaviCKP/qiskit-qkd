from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from qiskit_qkd import (
    DecoyIntensity,
    PostProcessingConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.postprocessing import (
    ClassicalPostProcessingResult,
    estimate_vacuum_weak_decoy_security,
    run_bb84_classical_postprocessing,
)


def _legacy_classical_result() -> ClassicalPostProcessingResult:
    return ClassicalPostProcessingResult(
        10,
        0,
        0,
        0.1,
        10,
        False,
        0,
        0,
        0,
        10,
        0,
        0,
        None,
    )


def _coherent_classical_fields() -> dict[str, Any]:
    return {
        "sifted_key_length": 10,
        "qber_sample_size": 2,
        "revealed_bits": 2,
        "estimated_qber": 0.2,
        "candidate_key_length": 8,
        "abort": False,
        "leak_ec": 2,
        "blocks_corrected": 1,
        "ambiguous_blocks": 0,
        "corrected_key_length": 8,
        "residual_mismatches": 0,
        "final_key_length": 8,
        "final_key_digest": None,
        "verification_passed": True,
        "qber_method": "revealed_sample",
        "threshold": 0.3,
        "threshold_exceeded": False,
        "threshold_decision_source": "classical_estimate",
        "verification_status": "passed",
        "qber_defined": True,
    }


def test_legacy_classical_construction_infers_qber_evidence() -> None:
    result = _legacy_classical_result()

    assert result.qber_defined is True
    assert result.qber_method == "full_sifted_key_diagnostic"
    assert result.threshold_decision_source == "disabled"
    assert result.verification_status == "not_performed"
    assert ClassicalPostProcessingResult(**result.to_dict()) == result


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"qber_method": "unavailable"}, "qber_method"),
        ({"qber_defined": False}, "qber_defined"),
        ({"revealed_bits": 1}, "revealed_bits"),
        ({"threshold_exceeded": True}, "threshold_exceeded"),
        ({"abort": True}, "abort"),
        (
            {
                "threshold": 0.1,
                "threshold_exceeded": False,
                "abort": False,
            },
            "threshold_exceeded",
        ),
        (
            {
                "threshold": 0.1,
                "threshold_exceeded": True,
                "abort": False,
            },
            "abort",
        ),
        (
            {"residual_mismatches": 1, "ambiguous_blocks": 1},
            "verification",
        ),
        ({"corrected_key_length": 7}, "corrected_key_length"),
        ({"final_key_length": 9}, "final_key_length"),
    ],
)
def test_classical_result_rejects_contradictory_states(
    overrides: Mapping[str, Any],
    message: str,
) -> None:
    fields = _coherent_classical_fields()
    fields.update(overrides)

    with pytest.raises((TypeError, ValueError), match=message):
        ClassicalPostProcessingResult(**fields)


def test_positive_sampling_fraction_reveals_one_bit_in_a_one_bit_key() -> None:
    result = run_bb84_classical_postprocessing(
        alice_bits=(0,),
        bob_bits=(1,),
        seed=1,
        config=PostProcessingConfig(
            qber_sample_fraction=0.5,
            qber_abort_threshold=None,
        ),
    )

    assert result.qber_sample_size == 1
    assert result.revealed_bits == 1
    assert result.qber_method == "revealed_sample"
    assert result.estimated_qber == 1.0
    assert result.candidate_key_length == 0
    assert result.verification_status == "not_applicable"
    assert result.final_key_length == 0


def _decoy_scenario() -> Scenario:
    return Scenario(
        pulses=3_000,
        clock_rate_hz=1_000.0,
        seed=1,
        source=SourceConfig(
            kind="decoy_weak_coherent",
            decoy_intensities=(
                DecoyIntensity("signal", 0.6, 0.7),
                DecoyIntensity("decoy", 0.2, 0.2),
                DecoyIntensity("vacuum", 0.0, 0.1),
            ),
        ),
    )


def _decoy_rows() -> dict[str, dict[str, Any]]:
    return {
        "signal": {
            "pulses": 1_000,
            "selection_fraction": 1 / 3,
            "detected": 100,
            "sifted": 50,
            "errors": 1,
            "gain": 0.1,
            "qber": 0.02,
        },
        "decoy": {
            "pulses": 1_000,
            "selection_fraction": 1 / 3,
            "detected": 40,
            "sifted": 20,
            "errors": 1,
            "gain": 0.04,
            "qber": 0.05,
        },
        "vacuum": {
            "pulses": 1_000,
            "selection_fraction": 1 / 3,
            "detected": 1,
            "sifted": 0,
            "errors": 0,
            "gain": 0.001,
            "qber": 0.0,
        },
    }


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    [
        (lambda rows: rows["signal"].pop("gain"), "MISSING_DECOY_FIELD"),
        (
            lambda rows: rows["signal"].__setitem__("gain", float("nan")),
            "NON_FINITE_DECOY_FIELD",
        ),
        (
            lambda rows: rows["signal"].__setitem__("gain", 1.01),
            "OUT_OF_RANGE_DECOY_RATE",
        ),
        (
            lambda rows: rows["signal"].__setitem__("selection_fraction", 1.01),
            "OUT_OF_RANGE_DECOY_RATE",
        ),
        (
            lambda rows: rows["signal"].__setitem__("sifted", 101),
            "INVALID_DECOY_COUNTS",
        ),
        (
            lambda rows: rows["signal"].__setitem__("qber", 0.03),
            "INCONSISTENT_DECOY_QBER",
        ),
    ],
)
def test_decoy_estimator_rejects_malformed_or_nonphysical_rows(
    mutate,
    reason_code: str,
) -> None:
    rows = _decoy_rows()
    mutate(rows)

    estimate = estimate_vacuum_weak_decoy_security(_decoy_scenario(), rows)

    assert estimate["valid"] is False
    assert estimate["secret_key_rate_bps"] == 0.0
    assert reason_code in estimate["reason_codes"]


def test_decoy_estimator_rejects_unconfigured_row_instead_of_using_it_as_signal(
) -> None:
    rows = _decoy_rows()
    rows["rogue"] = {
        **rows["signal"],
        "mean_photon_number": 2.0,
    }

    estimate = estimate_vacuum_weak_decoy_security(_decoy_scenario(), rows)

    assert estimate["valid"] is False
    assert "UNKNOWN_DECOY_INTENSITY" in estimate["reason_codes"]
    assert "signal_intensity" not in estimate


def test_decoy_estimator_rejects_missing_configured_row() -> None:
    rows = _decoy_rows()
    del rows["decoy"]

    estimate = estimate_vacuum_weak_decoy_security(_decoy_scenario(), rows)

    assert estimate["valid"] is False
    assert "MISSING_CONFIGURED_DECOY_ROW" in estimate["reason_codes"]


def test_valid_decoy_estimate_keeps_rates_and_fractions_physical() -> None:
    estimate = estimate_vacuum_weak_decoy_security(
        _decoy_scenario(),
        _decoy_rows(),
    )

    assert estimate["valid"] is True
    assert 0.0 <= estimate["basis_sift_factor"] <= 1.0
    assert 0.0 <= estimate["secret_fraction_per_signal_pulse"] <= 1.0
    assert 0.0 <= estimate["secret_key_rate_bps"] <= 1_000.0
