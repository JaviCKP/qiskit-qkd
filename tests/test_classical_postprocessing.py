from __future__ import annotations

from math import nextafter

import pytest

from qiskit_qkd import Event
from qiskit_qkd.config import PostProcessingConfig
from qiskit_qkd.postprocessing import (
    ClassicalPostProcessingResult,
    bb84_secret_fraction,
    extract_bb84_sifted_keys,
    qber,
    run_bb84_classical_postprocessing,
)


def test_extract_bb84_sifted_keys_uses_only_public_sifted_events() -> None:
    events = [
        Event(
            index=0,
            time_s=0.0,
            alice_bit=1,
            bob_bit=1,
            detected=True,
            sifted=True,
        ),
        Event(
            index=1,
            time_s=1.0,
            alice_bit=0,
            bob_bit=1,
            detected=True,
            sifted=False,
        ),
        Event(
            index=2,
            time_s=2.0,
            alice_bit=0,
            bob_bit=0,
            detected=True,
            sifted=True,
            detection_origin="dark",
        ),
    ]

    keys = extract_bb84_sifted_keys(events)

    assert keys.alice_bits == (1, 0)
    assert keys.bob_bits == (1, 0)


def test_qber_sampling_is_reproducible_and_removes_revealed_bits() -> None:
    config = PostProcessingConfig(qber_sample_fraction=0.5)

    first = run_bb84_classical_postprocessing(
        alice_bits=(0, 1, 1, 0),
        bob_bits=(0, 1, 0, 0),
        seed=101,
        config=config,
    )
    second = run_bb84_classical_postprocessing(
        alice_bits=(0, 1, 1, 0),
        bob_bits=(0, 1, 0, 0),
        seed=101,
        config=config,
    )

    assert first.to_dict() == second.to_dict()
    assert first.qber_sample_size == 2
    assert first.revealed_bits == 2
    assert first.candidate_key_length == 2


def test_postprocessing_aborts_before_reconciliation_when_qber_is_too_high() -> None:
    result = run_bb84_classical_postprocessing(
        alice_bits=(0, 0, 0, 0),
        bob_bits=(1, 1, 1, 1),
        seed=103,
        config=PostProcessingConfig(
            qber_sample_fraction=1.0,
            qber_abort_threshold=0.11,
        ),
    )

    assert result.abort is True
    assert result.corrected_key_length == 0
    assert result.final_key_length == 0
    assert result.final_key_digest is None


@pytest.mark.parametrize("qber_value", (0.5, nextafter(0.5, 1.0), 1.0))
def test_bb84_secret_fraction_is_zero_for_qber_at_or_above_half(
    qber_value: float,
) -> None:
    assert bb84_secret_fraction(
        qber_value,
        error_correction_efficiency=1.0,
    ) == 0.0


def test_qber_rejects_non_integer_counters() -> None:
    assert qber(1, 4) == 0.25

    for errors, sifted in (
        (True, 1),
        (0.5, 1),
        (0, True),
        (0, 1.5),
    ):
        with pytest.raises((TypeError, ValueError)):
            qber(errors, sifted)


def test_classical_postprocessing_result_rejects_non_boolean_abort() -> None:
    with pytest.raises(TypeError):
        ClassicalPostProcessingResult(
            sifted_key_length=0,
            qber_sample_size=0,
            revealed_bits=0,
            estimated_qber=0.0,
            candidate_key_length=0,
            abort=1,
            leak_ec=0,
            blocks_corrected=0,
            ambiguous_blocks=0,
            corrected_key_length=0,
            residual_mismatches=0,
            final_key_length=0,
            final_key_digest=None,
        )


def test_block_parity_reconciliation_corrects_single_error() -> None:
    result = run_bb84_classical_postprocessing(
        alice_bits=(0, 1, 1, 0),
        bob_bits=(0, 1, 0, 0),
        seed=107,
        config=PostProcessingConfig(
            qber_sample_fraction=0.0,
            qber_abort_threshold=0.5,
            reconciliation_block_size=4,
        ),
    )

    assert result.abort is False
    assert result.blocks_corrected == 1
    assert result.residual_mismatches == 0
    assert result.corrected_key_length == 4
    assert result.leak_ec > 0
    assert result.verification_passed is True
    assert result.final_key_length == 4


def test_residual_mismatches_fail_verification_and_withhold_final_key() -> None:
    result = run_bb84_classical_postprocessing(
        alice_bits=(0, 0, 0, 0, 0, 0, 0, 0),
        bob_bits=(1, 1, 0, 0, 0, 0, 0, 0),
        seed=113,
        config=PostProcessingConfig(
            qber_sample_fraction=0.0,
            qber_abort_threshold=None,
            reconciliation_block_size=8,
        ),
    )

    assert result.abort is False
    assert result.residual_mismatches == 2
    assert result.verification_passed is False
    assert result.final_key_length == 0
    assert result.final_key_digest is None


def test_privacy_amplification_reports_reproducible_digest_and_final_length() -> None:
    config = PostProcessingConfig(
        qber_sample_fraction=0.0,
        privacy_amplification_enabled=True,
        reconciliation_block_size=8,
    )

    first = run_bb84_classical_postprocessing(
        alice_bits=(0, 1) * 16,
        bob_bits=(0, 1) * 16,
        seed=109,
        config=config,
    )
    second = run_bb84_classical_postprocessing(
        alice_bits=(0, 1) * 16,
        bob_bits=(0, 1) * 16,
        seed=109,
        config=config,
    )

    assert first.final_key_length == 28
    assert first.final_key_digest is not None
    assert first.final_key_digest == second.final_key_digest


def test_privacy_amplification_outputs_no_key_for_high_qber() -> None:
    result = run_bb84_classical_postprocessing(
        alice_bits=(0,) * 16,
        bob_bits=(1,) * 16,
        seed=111,
        config=PostProcessingConfig(
            qber_sample_fraction=0.0,
            qber_abort_threshold=None,
            privacy_amplification_enabled=True,
            reconciliation_block_size=8,
        ),
    )

    assert result.abort is False
    assert result.estimated_qber == 1.0
    assert result.final_key_length == 0
    assert result.final_key_digest is None
