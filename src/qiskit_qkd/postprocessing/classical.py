"""Pedagogical classical post-processing for BB84 simulations."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    require_bool,
    require_non_negative_int,
    require_probability,
)
from qiskit_qkd.config import PostProcessingConfig
from qiskit_qkd.results import Event

from .key_rate import binary_entropy


def _validate_bits(name: str, bits: Sequence[int]) -> tuple[int, ...]:
    normalized = tuple(bits)
    invalid = [
        bit
        for bit in normalized
        if not isinstance(bit, int) or isinstance(bit, bool) or bit not in {0, 1}
    ]
    if invalid:
        raise ValueError(f"{name} must contain only 0 and 1 values")
    return normalized


def _mismatch_count(alice_bits: Sequence[int], bob_bits: Sequence[int]) -> int:
    return sum(alice != bob for alice, bob in zip(alice_bits, bob_bits, strict=True))


def _mismatch_rate(alice_bits: Sequence[int], bob_bits: Sequence[int]) -> float:
    if not alice_bits:
        return 0.0
    return _mismatch_count(alice_bits, bob_bits) / len(alice_bits)


def _parity(bits: Sequence[int]) -> int:
    return sum(bits) % 2


@dataclass(frozen=True, slots=True)
class BB84SiftedKeys:
    """Aligned Alice and Bob candidate strings after public BB84 sifting."""

    alice_bits: tuple[int, ...]
    bob_bits: tuple[int, ...]

    def __post_init__(self) -> None:
        alice_bits = _validate_bits("alice_bits", self.alice_bits)
        bob_bits = _validate_bits("bob_bits", self.bob_bits)
        if len(alice_bits) != len(bob_bits):
            raise ValueError("alice_bits and bob_bits must have the same length")
        object.__setattr__(self, "alice_bits", alice_bits)
        object.__setattr__(self, "bob_bits", bob_bits)


@dataclass(frozen=True, slots=True)
class ClassicalPostProcessingResult:
    """JSON-safe diagnostics for the pedagogical BB84 classical channel."""

    sifted_key_length: int
    qber_sample_size: int
    revealed_bits: int
    estimated_qber: float
    candidate_key_length: int
    abort: bool
    leak_ec: int
    blocks_corrected: int
    ambiguous_blocks: int
    corrected_key_length: int
    residual_mismatches: int
    final_key_length: int
    final_key_digest: str | None
    verification_passed: bool = False

    def __post_init__(self) -> None:
        for name in (
            "sifted_key_length",
            "qber_sample_size",
            "revealed_bits",
            "candidate_key_length",
            "leak_ec",
            "blocks_corrected",
            "ambiguous_blocks",
            "corrected_key_length",
            "residual_mismatches",
            "final_key_length",
        ):
            object.__setattr__(
                self,
                name,
                require_non_negative_int(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "estimated_qber",
            require_probability("estimated_qber", self.estimated_qber),
        )
        object.__setattr__(self, "abort", require_bool("abort", self.abort))
        object.__setattr__(
            self,
            "verification_passed",
            require_bool("verification_passed", self.verification_passed),
        )

    def to_dict(self) -> JSONObject:
        return {
            "sifted_key_length": self.sifted_key_length,
            "qber_sample_size": self.qber_sample_size,
            "revealed_bits": self.revealed_bits,
            "estimated_qber": self.estimated_qber,
            "candidate_key_length": self.candidate_key_length,
            "abort": self.abort,
            "leak_ec": self.leak_ec,
            "blocks_corrected": self.blocks_corrected,
            "ambiguous_blocks": self.ambiguous_blocks,
            "corrected_key_length": self.corrected_key_length,
            "residual_mismatches": self.residual_mismatches,
            "final_key_length": self.final_key_length,
            "final_key_digest": self.final_key_digest,
            "verification_passed": self.verification_passed,
        }


def extract_bb84_sifted_keys(events: Sequence[Event]) -> BB84SiftedKeys:
    """Build aligned BB84 key strings from publicly sifted event records."""

    alice_bits: list[int] = []
    bob_bits: list[int] = []
    for event in events:
        if not event.sifted:
            continue
        if event.alice_bit is None or event.bob_bit is None:
            raise ValueError("sifted events must contain Alice and Bob bits")
        alice_bits.append(event.alice_bit)
        bob_bits.append(event.bob_bit)
    return BB84SiftedKeys(tuple(alice_bits), tuple(bob_bits))


def run_bb84_classical_postprocessing(
    *,
    alice_bits: Sequence[int],
    bob_bits: Sequence[int],
    seed: int,
    config: PostProcessingConfig,
) -> ClassicalPostProcessingResult:
    """Estimate QBER, reconcile, and optionally hash a corrected BB84 key."""

    keys = BB84SiftedKeys(tuple(alice_bits), tuple(bob_bits))
    sample_indices = _qber_sample_indices(
        len(keys.alice_bits),
        config.qber_sample_fraction,
        seed,
    )
    estimated_qber = _estimated_qber(keys, sample_indices)
    candidate_alice, candidate_bob = _remove_revealed_bits(keys, sample_indices)
    threshold = config.qber_abort_threshold
    abort = threshold is not None and estimated_qber > threshold
    if abort:
        return ClassicalPostProcessingResult(
            sifted_key_length=len(keys.alice_bits),
            qber_sample_size=len(sample_indices),
            revealed_bits=len(sample_indices),
            estimated_qber=estimated_qber,
            candidate_key_length=len(candidate_alice),
            abort=True,
            leak_ec=0,
            blocks_corrected=0,
            ambiguous_blocks=0,
            corrected_key_length=0,
            residual_mismatches=0,
            final_key_length=0,
            final_key_digest=None,
        )

    reconciled = _reconcile_blocks(
        candidate_alice,
        candidate_bob,
        config.reconciliation_block_size,
    )
    verification_passed = reconciled.residual_mismatches == 0
    if verification_passed:
        final_key_length, final_key_digest = _privacy_amplify(
            corrected_bits=reconciled.corrected_alice_bits,
            enabled=config.privacy_amplification_enabled,
            estimated_qber=estimated_qber,
            leak_ec=reconciled.leak_ec,
            seed=seed,
        )
    else:
        # Residual mismatches mean Alice and Bob hold different strings, so a
        # verification exchange would reject the key instead of publishing it.
        final_key_length, final_key_digest = 0, None
    return ClassicalPostProcessingResult(
        sifted_key_length=len(keys.alice_bits),
        qber_sample_size=len(sample_indices),
        revealed_bits=len(sample_indices),
        estimated_qber=estimated_qber,
        candidate_key_length=len(candidate_alice),
        abort=False,
        leak_ec=reconciled.leak_ec,
        blocks_corrected=reconciled.blocks_corrected,
        ambiguous_blocks=reconciled.ambiguous_blocks,
        corrected_key_length=len(reconciled.corrected_alice_bits),
        residual_mismatches=reconciled.residual_mismatches,
        final_key_length=final_key_length,
        final_key_digest=final_key_digest,
        verification_passed=verification_passed,
    )


def _qber_sample_indices(
    sifted_length: int,
    sample_fraction: float,
    seed: int,
) -> frozenset[int]:
    sample_size = int(sifted_length * sample_fraction)
    if sample_size == 0:
        return frozenset()
    rng = random.Random(seed + 0xC1A551CA1)
    return frozenset(rng.sample(range(sifted_length), sample_size))


def _estimated_qber(keys: BB84SiftedKeys, sample_indices: frozenset[int]) -> float:
    if not sample_indices:
        return _mismatch_rate(keys.alice_bits, keys.bob_bits)
    errors = sum(
        keys.alice_bits[index] != keys.bob_bits[index]
        for index in sample_indices
    )
    return errors / len(sample_indices)


def _remove_revealed_bits(
    keys: BB84SiftedKeys,
    sample_indices: frozenset[int],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    alice_bits: list[int] = []
    bob_bits: list[int] = []
    for index, (alice_bit, bob_bit) in enumerate(
        zip(keys.alice_bits, keys.bob_bits, strict=True),
    ):
        if index in sample_indices:
            continue
        alice_bits.append(alice_bit)
        bob_bits.append(bob_bit)
    return tuple(alice_bits), tuple(bob_bits)


@dataclass(frozen=True, slots=True)
class _ReconciliationResult:
    corrected_alice_bits: tuple[int, ...]
    corrected_bob_bits: tuple[int, ...]
    leak_ec: int
    blocks_corrected: int
    ambiguous_blocks: int
    residual_mismatches: int


def _reconcile_blocks(
    alice_bits: tuple[int, ...],
    bob_bits: tuple[int, ...],
    block_size: int,
) -> _ReconciliationResult:
    corrected_bob = list(bob_bits)
    leak_ec = 0
    blocks_corrected = 0
    ambiguous_blocks = 0
    for start in range(0, len(alice_bits), block_size):
        end = min(start + block_size, len(alice_bits))
        alice_block = alice_bits[start:end]
        bob_block = tuple(corrected_bob[start:end])
        leak_ec += 1
        if _parity(alice_block) != _parity(bob_block):
            relative_index, revealed_parities = _locate_single_error(
                alice_block,
                bob_block,
            )
            leak_ec += revealed_parities
            corrected_bob[start + relative_index] ^= 1
            blocks_corrected += 1
        residual = _mismatch_count(alice_block, tuple(corrected_bob[start:end]))
        if residual > 0:
            ambiguous_blocks += 1
    corrected_bob_bits = tuple(corrected_bob)
    return _ReconciliationResult(
        corrected_alice_bits=alice_bits,
        corrected_bob_bits=corrected_bob_bits,
        leak_ec=leak_ec,
        blocks_corrected=blocks_corrected,
        ambiguous_blocks=ambiguous_blocks,
        residual_mismatches=_mismatch_count(alice_bits, corrected_bob_bits),
    )


def _locate_single_error(
    alice_block: tuple[int, ...],
    bob_block: tuple[int, ...],
) -> tuple[int, int]:
    low = 0
    high = len(alice_block)
    revealed_parities = 0
    while high - low > 1:
        mid = (low + high) // 2
        revealed_parities += 1
        if _parity(alice_block[low:mid]) != _parity(bob_block[low:mid]):
            high = mid
        else:
            low = mid
    return low, revealed_parities


def _privacy_amplify(
    *,
    corrected_bits: tuple[int, ...],
    enabled: bool,
    estimated_qber: float,
    leak_ec: int,
    seed: int,
) -> tuple[int, str | None]:
    if not enabled:
        return len(corrected_bits), None
    if estimated_qber >= 0.5:
        return 0, None
    final_length = max(
        0,
        int(len(corrected_bits) * (1.0 - binary_entropy(estimated_qber)) - leak_ec),
    )
    if final_length == 0:
        return 0, None
    bitstring = "".join(str(bit) for bit in corrected_bits)
    payload = f"bb84-pa|{seed}|{final_length}|{bitstring}".encode()
    return final_length, hashlib.sha256(payload).hexdigest()
