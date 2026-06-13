"""Asymptotic decoy-state security estimators for BB84."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from qiskit_qkd._json import JSONObject
from qiskit_qkd.config import Scenario

from .key_rate import binary_entropy


def estimate_vacuum_weak_decoy_security(
    scenario: Scenario,
    decoy_rows: Mapping[str, Mapping[str, Any]],
) -> JSONObject:
    """Estimate asymptotic vacuum+weak decoy single-photon bounds.

    The estimator uses the common three-intensity BB84 setting with one signal
    intensity ``mu``, one weak decoy ``nu`` and one vacuum decoy. It returns
    conservative clipped bounds suitable for simulation diagnostics, not a
    finite-key or composable security proof.
    """

    warnings: list[str] = []
    selected = _select_vacuum_weak_rows(scenario, decoy_rows)
    if selected is None:
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            ["requires one signal, one weak decoy, and one vacuum intensity"],
        )

    signal, weak, vacuum = selected
    signal_name, mu, signal_row = signal
    weak_name, nu, weak_row = weak
    vacuum_name, _vacuum_mu, vacuum_row = vacuum

    q_mu = _row_float(signal_row, "gain")
    q_nu = _row_float(weak_row, "gain")
    y0 = _row_float(vacuum_row, "gain")
    e_mu = _row_float(signal_row, "qber")
    e_nu = _row_float(weak_row, "qber")
    signal_detected = _row_float(signal_row, "detected")
    signal_sifted = _row_float(signal_row, "sifted")
    signal_selection_fraction = _row_float(
        signal_row,
        "selection_fraction",
        default=_row_float(signal_row, "pulses") / scenario.pulses,
    )
    basis_sift_factor = (
        signal_sifted / signal_detected if signal_detected > 0.0 else 0.0
    )

    denominator = mu * nu - nu**2
    if denominator <= 0.0:
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            ["signal intensity must be greater than weak decoy intensity"],
        )

    y1_raw = (mu / denominator) * (
        q_nu * math.exp(nu)
        - q_mu * math.exp(mu) * (nu**2 / mu**2)
        - ((mu**2 - nu**2) / mu**2) * y0
    )
    y1_lower = _clip_probability(y1_raw)
    if y1_raw < 0.0:
        warnings.append("single-photon yield lower bound clipped to 0")
    if y1_raw > 1.0:
        warnings.append("single-photon yield lower bound clipped to 1")

    q1_lower = mu * math.exp(-mu) * y1_lower
    if y1_lower == 0.0 or nu == 0.0:
        e1_upper = 1.0
        warnings.append("single-photon error upper bound set to 1")
    else:
        e1_raw = (e_nu * q_nu * math.exp(nu) - 0.5 * y0) / (nu * y1_lower)
        e1_upper = _clip_probability(max(0.0, e1_raw))
        if e1_raw < 0.0:
            warnings.append("single-photon error upper bound clipped to 0")
        if e1_raw > 1.0:
            warnings.append("single-photon error upper bound clipped to 1")

    error_correction_efficiency = (
        scenario.post_processing.error_correction_efficiency
    )
    privacy_term = q1_lower * _bb84_privacy_multiplier(e1_upper)
    leakage_term = (
        error_correction_efficiency
        * q_mu
        * _bb84_error_entropy(e_mu)
    )
    secret_fraction_per_signal_pulse = basis_sift_factor * max(
        0.0,
        privacy_term - leakage_term,
    )
    secret_key_rate_bps = (
        scenario.clock_rate_hz
        * signal_selection_fraction
        * secret_fraction_per_signal_pulse
    )

    return {
        "valid": True,
        "method": "vacuum_weak_asymptotic",
        "signal_intensity": signal_name,
        "weak_decoy_intensity": weak_name,
        "decoy_intensity": weak_name,
        "vacuum_intensity": vacuum_name,
        "signal_mean_photon_number": mu,
        "weak_decoy_mean_photon_number": nu,
        "signal_gain": q_mu,
        "weak_decoy_gain": q_nu,
        "vacuum_yield": y0,
        "signal_qber": e_mu,
        "weak_decoy_qber": e_nu,
        "basis_sift_factor": basis_sift_factor,
        "single_photon_yield_lower_bound": y1_lower,
        "single_photon_gain_lower_bound": q1_lower,
        "single_photon_error_rate_upper_bound": e1_upper,
        "secret_fraction_per_signal_pulse": secret_fraction_per_signal_pulse,
        "secret_key_rate_bps": secret_key_rate_bps,
        "error_correction_efficiency": error_correction_efficiency,
        "warnings": warnings,
    }


IntensityRow = tuple[str, float, Mapping[str, Any]]


def _select_vacuum_weak_rows(
    scenario: Scenario,
    decoy_rows: Mapping[str, Mapping[str, Any]],
) -> tuple[IntensityRow, IntensityRow, IntensityRow] | None:
    rows: list[IntensityRow] = []
    configured = {
        intensity.name: intensity.mean_photon_number
        for intensity in scenario.source.decoy_intensities
    }
    for name, row in decoy_rows.items():
        if name == "security":
            continue
        if not isinstance(row, Mapping):
            continue
        mu = configured.get(name, _row_float(row, "mean_photon_number", default=-1.0))
        if mu < 0.0:
            continue
        rows.append((name, mu, row))

    vacuum_candidates = [row for row in rows if row[1] == 0.0]
    positive = sorted((row for row in rows if row[1] > 0.0), key=lambda item: item[1])
    if not vacuum_candidates or len(positive) < 2:
        return None
    signal = positive[-1]
    weak = positive[-2]
    return signal, weak, vacuum_candidates[0]


def _row_float(
    row: Mapping[str, Any],
    key: str,
    *,
    default: float = 0.0,
) -> float:
    value = row.get(key, default)
    if value is None:
        return default
    return float(value)


def _clip_probability(value: float) -> float:
    return min(1.0, max(0.0, value))


def _bb84_privacy_multiplier(error_rate: float) -> float:
    error_rate = _clip_probability(error_rate)
    if error_rate >= 0.5:
        return 0.0
    return 1.0 - binary_entropy(error_rate)


def _bb84_error_entropy(error_rate: float) -> float:
    error_rate = _clip_probability(error_rate)
    if error_rate >= 0.5:
        return 1.0
    return binary_entropy(error_rate)


def _invalid_estimate(method: str, warnings: list[str]) -> JSONObject:
    return {
        "valid": False,
        "method": method,
        "secret_key_rate_bps": 0.0,
        "warnings": warnings,
    }
