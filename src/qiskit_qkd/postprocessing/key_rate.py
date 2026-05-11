"""Pedagogical BB84 QBER and asymptotic key-rate helpers."""

from __future__ import annotations

from math import log2

from qiskit_qkd._validation import require_minimum_number, require_probability


def binary_entropy(probability: float) -> float:
    """Return h2(p) for a binary random variable."""

    probability = require_probability("probability", probability)
    if probability in {0.0, 1.0}:
        return 0.0
    return -probability * log2(probability) - (1.0 - probability) * log2(
        1.0 - probability,
    )


def qber(errors: int, sifted: int) -> float:
    """Return QBER from sifted-key error counts."""

    if sifted < 0:
        raise ValueError("sifted must be non-negative")
    if errors < 0:
        raise ValueError("errors must be non-negative")
    if errors > sifted:
        raise ValueError("errors must not exceed sifted")
    if sifted == 0:
        return 0.0
    return errors / sifted


def bb84_secret_fraction(
    qber_value: float,
    *,
    error_correction_efficiency: float,
) -> float:
    """Return max(0, 1 - f_ec h2(Q) - h2(Q)) for simplified BB84."""

    qber_value = require_probability("qber", qber_value)
    error_correction_efficiency = require_minimum_number(
        "error_correction_efficiency",
        error_correction_efficiency,
        1.0,
    )
    entropy = binary_entropy(qber_value)
    return max(0.0, 1.0 - error_correction_efficiency * entropy - entropy)
