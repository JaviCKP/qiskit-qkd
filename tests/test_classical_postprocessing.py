from __future__ import annotations

from qiskit_qkd import Event
from qiskit_qkd.config import PostProcessingConfig
from qiskit_qkd.postprocessing import (
    extract_bb84_sifted_keys,
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
