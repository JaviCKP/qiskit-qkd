"""Pedagogical classical post-processing for BB84 simulations."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    require_bool,
    require_choice,
    require_non_negative_int,
    require_optional_probability,
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


def _mismatch_rate(
    alice_bits: Sequence[int],
    bob_bits: Sequence[int],
) -> float | None:
    if not alice_bits:
        return None
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
    estimated_qber: float | None
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
    qber_method: str | None = None
    threshold: float | None = None
    threshold_exceeded: bool | None = None
    threshold_decision_source: str | None = None
    verification_status: str | None = None
    qber_defined: bool | None = None

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
            require_optional_probability("estimated_qber", self.estimated_qber),
        )
        object.__setattr__(self, "abort", require_bool("abort", self.abort))
        object.__setattr__(
            self,
            "verification_passed",
            require_bool("verification_passed", self.verification_passed),
        )
        qber_defined = (
            self.estimated_qber is not None
            if self.qber_defined is None
            else require_bool("qber_defined", self.qber_defined)
        )
        if qber_defined != (self.estimated_qber is not None):
            raise ValueError(
                "qber_defined must be true exactly when estimated_qber is defined",
            )
        object.__setattr__(self, "qber_defined", qber_defined)

        expected_qber_method = (
            "unavailable"
            if not qber_defined
            else "revealed_sample"
            if self.qber_sample_size > 0
            else "full_sifted_key_diagnostic"
        )
        qber_method = (
            expected_qber_method
            if self.qber_method is None
            else require_choice(
                "qber_method",
                self.qber_method,
                {
                    "revealed_sample",
                    "full_sifted_key_diagnostic",
                    "unavailable",
                },
            )
        )
        if qber_method != expected_qber_method:
            raise ValueError(
                "qber_method must agree with qber_sample_size and estimated_qber; "
                f"expected {expected_qber_method!r}, got {qber_method!r}",
            )
        object.__setattr__(self, "qber_method", qber_method)

        object.__setattr__(
            self,
            "threshold",
            require_optional_probability("threshold", self.threshold),
        )
        if self.threshold_exceeded is not None:
            object.__setattr__(
                self,
                "threshold_exceeded",
                require_bool("threshold_exceeded", self.threshold_exceeded),
            )
        threshold_decision_source = (
            None
            if self.threshold_decision_source is None
            else require_choice(
                "threshold_decision_source",
                self.threshold_decision_source,
                {
                    "classical_estimate",
                    "disabled",
                    "unavailable",
                },
            )
        )
        verification_status = (
            None
            if self.verification_status is None
            else require_choice(
                "verification_status",
                self.verification_status,
                {"passed", "failed", "not_performed", "not_applicable", "unknown"},
            )
        )

        if self.qber_sample_size > self.sifted_key_length:
            raise ValueError(
                "qber_sample_size must not exceed sifted_key_length; "
                f"got {self.qber_sample_size} > {self.sifted_key_length}",
            )
        if self.revealed_bits != self.qber_sample_size:
            raise ValueError(
                "revealed_bits must equal qber_sample_size; "
                f"got {self.revealed_bits} and {self.qber_sample_size}",
            )
        expected_candidate_length = self.sifted_key_length - self.revealed_bits
        if self.candidate_key_length != expected_candidate_length:
            raise ValueError(
                "candidate_key_length must equal sifted_key_length - revealed_bits; "
                f"expected {expected_candidate_length}, got "
                f"{self.candidate_key_length}",
            )
        if qber_defined and self.sifted_key_length == 0:
            raise ValueError(
                "estimated_qber must be None when sifted_key_length is 0",
            )

        threshold_exceeded = self.threshold_exceeded
        if self.threshold is not None:
            expected_threshold_exceeded = (
                None
                if self.estimated_qber is None
                else self.estimated_qber > self.threshold
            )
            expected_source = (
                "unavailable"
                if expected_threshold_exceeded is None
                else "classical_estimate"
            )
            if (
                threshold_exceeded is not None
                and threshold_exceeded != expected_threshold_exceeded
            ):
                raise ValueError(
                    "threshold_exceeded must equal estimated_qber > threshold; "
                    f"expected {expected_threshold_exceeded}, got {threshold_exceeded}",
                )
            threshold_exceeded = expected_threshold_exceeded
            if (
                threshold_decision_source is not None
                and threshold_decision_source != expected_source
            ):
                raise ValueError(
                    "threshold_decision_source must agree with available QBER "
                    f"evidence; expected {expected_source!r}, got "
                    f"{threshold_decision_source!r}",
                )
            threshold_decision_source = expected_source
            expected_abort = expected_threshold_exceeded is True
            if self.abort != expected_abort:
                raise ValueError(
                    "abort must equal threshold_exceeded when a threshold is enabled; "
                    f"expected {expected_abort}, got {self.abort}",
                )
        elif threshold_decision_source is None:
            # The legacy constructor only carried ``abort``. Preserve those
            # payloads without pretending that their threshold is known.
            threshold_decision_source = "unavailable" if self.abort else "disabled"
            threshold_exceeded = True if self.abort else None
        elif threshold_decision_source == "disabled":
            if threshold_exceeded is not None or self.abort:
                raise ValueError(
                    "threshold_exceeded must be None and abort false when threshold "
                    "decision is disabled",
                )
        elif not (
            threshold_decision_source == "unavailable"
            and threshold_exceeded is True
            and self.abort
        ):
            raise ValueError(
                "a missing threshold only supports a disabled decision or a legacy "
                "unavailable abort projection",
            )
        object.__setattr__(self, "threshold_exceeded", threshold_exceeded)
        object.__setattr__(
            self,
            "threshold_decision_source",
            threshold_decision_source,
        )

        if self.abort:
            if any(
                value != 0
                for value in (
                    self.leak_ec,
                    self.blocks_corrected,
                    self.ambiguous_blocks,
                    self.corrected_key_length,
                    self.residual_mismatches,
                    self.final_key_length,
                )
            ):
                raise ValueError(
                    "abort requires zero reconciliation, verification, and final-key "
                    "outputs",
                )
            if self.final_key_digest is not None or self.verification_passed:
                raise ValueError(
                    "abort requires no final_key_digest and failed verification",
                )
            expected_verification_status = "not_performed"
        else:
            if self.corrected_key_length != self.candidate_key_length:
                raise ValueError(
                    "corrected_key_length must equal candidate_key_length when abort "
                    f"is false; got {self.corrected_key_length} and "
                    f"{self.candidate_key_length}",
                )
            for name in ("leak_ec", "blocks_corrected", "ambiguous_blocks"):
                value = getattr(self, name)
                if value > self.corrected_key_length:
                    raise ValueError(
                        f"{name} must not exceed corrected_key_length; got {value} > "
                        f"{self.corrected_key_length}",
                    )
            if self.residual_mismatches > self.corrected_key_length:
                raise ValueError(
                    "residual_mismatches must not exceed corrected_key_length; "
                    f"got {self.residual_mismatches} > {self.corrected_key_length}",
                )
            if (self.ambiguous_blocks > 0) != (self.residual_mismatches > 0):
                raise ValueError(
                    "ambiguous_blocks must be positive exactly when "
                    "residual_mismatches are present",
                )
            if self.corrected_key_length == 0:
                expected_verification_status = "not_applicable"
            elif self.residual_mismatches > 0:
                expected_verification_status = "failed"
            elif self.verification_passed:
                expected_verification_status = "passed"
            else:
                expected_verification_status = "not_performed"

        if verification_status is None or verification_status == "unknown":
            verification_status = expected_verification_status
        elif verification_status != expected_verification_status:
            raise ValueError(
                "verification_status must agree with abort, corrected length, residual "
                f"mismatches, and verification_passed; expected "
                f"{expected_verification_status!r}, got {verification_status!r}",
            )
        if self.verification_passed != (verification_status == "passed"):
            raise ValueError(
                "verification_passed must agree with verification_status='passed'",
            )
        object.__setattr__(self, "verification_status", verification_status)

        if self.final_key_length > self.corrected_key_length:
            raise ValueError(
                "final_key_length must not exceed corrected_key_length; "
                f"got {self.final_key_length} > {self.corrected_key_length}",
            )
        if self.final_key_length > 0 and not self.verification_passed:
            raise ValueError(
                "a positive final_key_length requires verification_passed=true",
            )
        if self.final_key_length == 0 and self.final_key_digest is not None:
            raise ValueError(
                "final_key_digest must be None when final_key_length is 0",
            )
        if self.final_key_digest is not None:
            if not isinstance(self.final_key_digest, str):
                raise TypeError("final_key_digest must be a string or None")
            if not self.final_key_digest.strip():
                raise ValueError("final_key_digest must not be empty")

    def to_dict(self) -> JSONObject:
        return {
            "sifted_key_length": self.sifted_key_length,
            "qber_sample_size": self.qber_sample_size,
            "revealed_bits": self.revealed_bits,
            "estimated_qber": self.estimated_qber,
            "qber_defined": self.qber_defined,
            "qber_method": self.qber_method,
            "threshold": self.threshold,
            "threshold_exceeded": self.threshold_exceeded,
            "threshold_decision_source": self.threshold_decision_source,
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
            "verification_status": self.verification_status,
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
    threshold_exceeded = (
        None
        if threshold is None or estimated_qber is None
        else estimated_qber > threshold
    )
    threshold_decision_source = (
        "disabled"
        if threshold is None
        else "unavailable"
        if estimated_qber is None
        else "classical_estimate"
    )
    qber_method = (
        "unavailable"
        if not keys.alice_bits
        else "revealed_sample"
        if sample_indices
        else "full_sifted_key_diagnostic"
    )
    abort = threshold_exceeded is True
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
            qber_method=qber_method,
            threshold=threshold,
            threshold_exceeded=threshold_exceeded,
            threshold_decision_source=threshold_decision_source,
            verification_status="not_performed",
        )

    reconciled = _reconcile_blocks(
        candidate_alice,
        candidate_bob,
        config.reconciliation_block_size,
    )
    verification_status = (
        "not_applicable"
        if not candidate_alice
        else "passed"
        if reconciled.residual_mismatches == 0
        else "failed"
    )
    verification_passed = verification_status == "passed"
    if verification_passed:
        if estimated_qber is None:
            raise RuntimeError("a non-empty candidate key must have a QBER estimate")
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
        qber_method=qber_method,
        threshold=threshold,
        threshold_exceeded=threshold_exceeded,
        threshold_decision_source=threshold_decision_source,
        verification_status=verification_status,
    )


def _qber_sample_indices(
    sifted_length: int,
    sample_fraction: float,
    seed: int,
) -> frozenset[int]:
    sample_size = int(sifted_length * sample_fraction)
    if sifted_length == 0 or sample_fraction == 0.0:
        return frozenset()
    sample_size = min(sifted_length, max(1, sample_size))
    rng = random.Random(seed + 0xC1A551CA1)
    return frozenset(rng.sample(range(sifted_length), sample_size))


def _estimated_qber(
    keys: BB84SiftedKeys,
    sample_indices: frozenset[int],
) -> float | None:
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
