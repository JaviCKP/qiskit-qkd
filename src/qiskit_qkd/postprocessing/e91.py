"""Classical E91 sifting and Bell-test helpers."""

from __future__ import annotations

from collections.abc import Mapping

from qiskit_qkd._validation import require_bool, require_non_negative_int

SettingPair = tuple[int, int]
ChshTerm = tuple[int, int, int]


def setting_pair_label(alice_setting: int, bob_setting: int) -> str:
    """Return a stable public label for an E91 setting pair."""

    alice_setting = require_non_negative_int("alice_setting", alice_setting)
    bob_setting = require_non_negative_int("bob_setting", bob_setting)
    return f"A{alice_setting}/B{bob_setting}"


def corrected_e91_bob_key_bit(
    bob_bit: int,
    *,
    bob_key_bit_flip: bool,
) -> int:
    """Return Bob's key bit after the configured singlet anticorrelation flip."""

    if (
        not isinstance(bob_bit, int)
        or isinstance(bob_bit, bool)
        or bob_bit not in {0, 1}
    ):
        raise ValueError("bob_bit must be 0 or 1")
    bob_key_bit_flip = require_bool("bob_key_bit_flip", bob_key_bit_flip)
    return 1 - bob_bit if bob_key_bit_flip else bob_bit


def e91_key_error(
    alice_bit: int,
    bob_bit: int,
    *,
    bob_key_bit_flip: bool,
) -> bool:
    """Return whether a sifted E91 key round disagrees after Bob correction."""

    if (
        not isinstance(alice_bit, int)
        or isinstance(alice_bit, bool)
        or alice_bit not in {0, 1}
    ):
        raise ValueError("alice_bit must be 0 or 1")
    return alice_bit != corrected_e91_bob_key_bit(
        bob_bit,
        bob_key_bit_flip=bob_key_bit_flip,
    )


def correlation_from_counts(*, same: int, different: int) -> float | None:
    """Return E=(N_same-N_different)/(N_same+N_different)."""

    same = require_non_negative_int("same", same)
    different = require_non_negative_int("different", different)
    total = same + different
    if total == 0:
        return None
    return (same - different) / total


def chsh_s_from_correlations(
    correlations: Mapping[SettingPair, float | None],
    chsh_terms: tuple[ChshTerm, ...],
) -> float | None:
    """Return |sum c_ab E(a,b)| when all CHSH terms are available."""

    total = 0.0
    for alice_setting, bob_setting, coefficient in chsh_terms:
        correlation = correlations.get((alice_setting, bob_setting))
        if correlation is None:
            return None
        total += coefficient * correlation
    return abs(total)
