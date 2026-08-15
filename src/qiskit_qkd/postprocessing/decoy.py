"""Asymptotic decoy-state security estimators for BB84."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
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
    selected, validation_codes, validation_reasons = _select_vacuum_weak_rows(
        scenario,
        decoy_rows,
    )
    if validation_codes:
        data_status = (
            "insufficient_data"
            if set(validation_codes) == {"MISSING_CONFIGURED_DECOY_ROW"}
            else "invalid_data"
        )
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            validation_reasons,
            reason_codes=validation_codes,
            data_status=data_status,
        )
    if selected is None:
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            ["requires one signal, one weak decoy, and one vacuum intensity"],
            reason_codes=["MISSING_VACUUM_WEAK_INTENSITIES"],
        )

    signal, weak, vacuum = selected

    unavailable_qber_codes: list[str] = []
    unavailable_qber_reasons: list[str] = []
    if not signal.qber_defined:
        unavailable_qber_codes.append("SIGNAL_QBER_UNAVAILABLE")
        unavailable_qber_reasons.append(
            "Signal-intensity QBER requires a non-empty sifted sample.",
        )
    if not weak.qber_defined:
        unavailable_qber_codes.append("WEAK_DECOY_QBER_UNAVAILABLE")
        unavailable_qber_reasons.append(
            "Weak-decoy QBER requires a non-empty sifted sample.",
        )
    if unavailable_qber_codes:
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            unavailable_qber_reasons,
            reason_codes=unavailable_qber_codes,
        )

    mu = signal.mean_photon_number
    nu = weak.mean_photon_number
    q_mu = signal.gain
    q_nu = weak.gain
    y0 = vacuum.gain
    e_mu = signal.qber
    e_nu = weak.qber
    basis_sift_factor = (
        signal.sifted / signal.detected if signal.detected > 0 else 0.0
    )

    try:
        mu_squared = mu**2
        nu_squared = nu**2
        exp_mu = math.exp(mu)
        exp_nu = math.exp(nu)
        denominator = mu * nu - nu_squared
    except OverflowError:
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            [
                "Configured decoy intensities overflow the asymptotic estimator; "
                "use finite weak-coherent mean photon numbers.",
            ],
            reason_codes=["NUMERICAL_DECOY_DOMAIN"],
            data_status="invalid_data",
        )
    if not all(
        math.isfinite(value)
        for value in (mu_squared, nu_squared, exp_mu, exp_nu, denominator)
    ):
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            [
                "Configured decoy intensities produce non-finite estimator terms; "
                "use smaller weak-coherent mean photon numbers.",
            ],
            reason_codes=["NUMERICAL_DECOY_DOMAIN"],
            data_status="invalid_data",
        )
    if denominator <= 0.0:
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            ["signal intensity must be greater than weak decoy intensity"],
            reason_codes=["INVALID_INTENSITY_ORDER"],
        )

    y1_raw = (mu / denominator) * (
        q_nu * exp_nu
        - q_mu * exp_mu * (nu_squared / mu_squared)
        - ((mu_squared - nu_squared) / mu_squared) * y0
    )
    if not math.isfinite(y1_raw):
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            ["Decoy observations produce a non-finite single-photon yield bound."],
            reason_codes=["NON_FINITE_DECOY_ESTIMATE"],
            data_status="invalid_data",
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
        e1_raw = (e_nu * q_nu * exp_nu - 0.5 * y0) / (nu * y1_lower)
        if not math.isfinite(e1_raw):
            return _invalid_estimate(
                "vacuum_weak_asymptotic",
                [
                    "Decoy observations produce a non-finite single-photon error "
                    "bound.",
                ],
                reason_codes=["NON_FINITE_DECOY_ESTIMATE"],
                data_status="invalid_data",
            )
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
    raw_secret_fraction = basis_sift_factor * max(
        0.0,
        privacy_term - leakage_term,
    )
    secret_fraction_per_signal_pulse = _clip_probability(raw_secret_fraction)
    if raw_secret_fraction > 1.0:
        warnings.append("secret fraction per signal pulse clipped to 1")
    secret_key_rate_bps = (
        scenario.clock_rate_hz
        * signal.selection_fraction
        * secret_fraction_per_signal_pulse
    )
    if not math.isfinite(secret_key_rate_bps):
        return _invalid_estimate(
            "vacuum_weak_asymptotic",
            ["Decoy observations produce a non-finite secret-key rate."],
            reason_codes=["NON_FINITE_DECOY_ESTIMATE"],
            data_status="invalid_data",
        )
    secret_key_rate_bps = min(scenario.clock_rate_hz, secret_key_rate_bps)

    return {
        "valid": True,
        "data_status": "available",
        "method": "vacuum_weak_asymptotic",
        "signal_intensity": signal.name,
        "weak_decoy_intensity": weak.name,
        "decoy_intensity": weak.name,
        "vacuum_intensity": vacuum.name,
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
        "security_scope": "pedagogical_asymptotic_diagnostic",
        "finite_key": False,
        "composable": False,
        "reason_codes": [],
        "reasons": [],
        "warnings": warnings,
    }


@dataclass(frozen=True, slots=True)
class _ValidatedIntensityRow:
    name: str
    mean_photon_number: float
    pulses: int
    detected: int
    sifted: int
    errors: int
    gain: float
    qber: float
    qber_defined: bool
    selection_fraction: float


def _select_vacuum_weak_rows(
    scenario: Scenario,
    decoy_rows: Mapping[str, Mapping[str, Any]],
) -> tuple[
    tuple[
        _ValidatedIntensityRow,
        _ValidatedIntensityRow,
        _ValidatedIntensityRow,
    ]
    | None,
    list[str],
    list[str],
]:
    reason_codes: list[str] = []
    reasons: list[str] = []

    def add_issue(code: str, reason: str) -> None:
        if code not in reason_codes:
            reason_codes.append(code)
        reasons.append(reason)

    if not isinstance(decoy_rows, Mapping):
        add_issue(
            "INVALID_DECOY_ROWS",
            f"decoy_rows must be a mapping, got {type(decoy_rows).__name__}.",
        )
        return None, reason_codes, reasons

    configured = {
        intensity.name: intensity.mean_photon_number
        for intensity in scenario.source.decoy_intensities
    }
    supplied_names = {name for name in decoy_rows if name != "security"}
    unknown_names = supplied_names - set(configured)
    if unknown_names:
        names = ", ".join(sorted(repr(name) for name in unknown_names))
        add_issue(
            "UNKNOWN_DECOY_INTENSITY",
            f"Decoy rows contain unconfigured intensity name(s): {names}. Remove "
            "them or add matching source.decoy_intensities entries.",
        )
    missing_names = set(configured) - supplied_names
    if missing_names:
        names = ", ".join(sorted(missing_names))
        add_issue(
            "MISSING_CONFIGURED_DECOY_ROW",
            f"Decoy rows are missing configured intensity name(s): {names}. Run "
            "enough pulses to observe every configured class.",
        )
    if reason_codes:
        return None, reason_codes, reasons

    rows: list[_ValidatedIntensityRow] = []
    for name, mean_photon_number in configured.items():
        row = decoy_rows[name]
        if not isinstance(row, Mapping):
            add_issue(
                "INVALID_DECOY_ROW",
                f"Decoy row {name!r} must be a mapping, got {type(row).__name__}.",
            )
            continue
        validated = _validate_decoy_row(
            name=name,
            mean_photon_number=mean_photon_number,
            row=row,
            scenario_pulses=scenario.pulses,
            add_issue=add_issue,
        )
        if validated is not None:
            rows.append(validated)

    if reason_codes:
        return None, reason_codes, reasons
    if sum(row.pulses for row in rows) != scenario.pulses:
        add_issue(
            "DECOY_PULSE_TOTAL_MISMATCH",
            "The sum of configured decoy-row pulses must equal scenario.pulses; "
            f"got {sum(row.pulses for row in rows)} and {scenario.pulses}.",
        )
        return None, reason_codes, reasons

    vacuum_candidates = [row for row in rows if row.mean_photon_number == 0.0]
    positive = sorted(
        (row for row in rows if row.mean_photon_number > 0.0),
        key=lambda item: item.mean_photon_number,
    )
    if len(vacuum_candidates) != 1 or len(positive) != 2:
        return None, reason_codes, reasons
    return (positive[-1], positive[0], vacuum_candidates[0]), reason_codes, reasons


def _validate_decoy_row(
    *,
    name: str,
    mean_photon_number: float,
    row: Mapping[str, Any],
    scenario_pulses: int,
    add_issue: Callable[[str, str], None],
) -> _ValidatedIntensityRow | None:
    required = {"pulses", "detected", "sifted", "errors", "gain", "qber"}
    missing = sorted(required - set(row))
    if missing:
        add_issue(
            "MISSING_DECOY_FIELD",
            f"Decoy row {name!r} is missing required field(s): {', '.join(missing)}.",
        )
        return None

    counts: dict[str, int] = {}
    for key in ("pulses", "detected", "sifted", "errors"):
        value = row[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            add_issue(
                "INVALID_DECOY_COUNT",
                f"Decoy row {name!r} field {key!r} must be a non-negative "
                f"integer, got {value!r}.",
            )
            return None
        counts[key] = value

    if not (
        counts["errors"] <= counts["sifted"]
        <= counts["detected"]
        <= counts["pulses"]
    ):
        add_issue(
            "INVALID_DECOY_COUNTS",
            (
                f"Decoy row {name!r} must satisfy errors <= sifted <= detected "
                "<= pulses; got errors={errors}, sifted={sifted}, "
                "detected={detected}, pulses={pulses}."
            ).format(**counts),
        )
        return None

    rates: dict[str, float] = {}
    for key in ("gain", "qber"):
        value = row[key]
        if not isinstance(value, int | float) or isinstance(value, bool):
            add_issue(
                "INVALID_DECOY_RATE",
                f"Decoy row {name!r} field {key!r} must be numeric, got "
                f"{value!r}.",
            )
            return None
        normalized = float(value)
        if not math.isfinite(normalized):
            add_issue(
                "NON_FINITE_DECOY_FIELD",
                f"Decoy row {name!r} field {key!r} must be finite, got "
                f"{value!r}.",
            )
            return None
        if not 0.0 <= normalized <= 1.0:
            add_issue(
                "OUT_OF_RANGE_DECOY_RATE",
                f"Decoy row {name!r} field {key!r} must be between 0 and 1, "
                f"got {normalized}.",
            )
            return None
        rates[key] = normalized

    raw_selection_fraction = row.get(
        "selection_fraction",
        counts["pulses"] / scenario_pulses,
    )
    if (
        not isinstance(raw_selection_fraction, int | float)
        or isinstance(raw_selection_fraction, bool)
    ):
        add_issue(
            "INVALID_DECOY_RATE",
            f"Decoy row {name!r} field 'selection_fraction' must be numeric, got "
            f"{raw_selection_fraction!r}.",
        )
        return None
    selection_fraction = float(raw_selection_fraction)
    if not math.isfinite(selection_fraction):
        add_issue(
            "NON_FINITE_DECOY_FIELD",
            f"Decoy row {name!r} field 'selection_fraction' must be finite, got "
            f"{raw_selection_fraction!r}.",
        )
        return None
    if not 0.0 <= selection_fraction <= 1.0:
        add_issue(
            "OUT_OF_RANGE_DECOY_RATE",
            f"Decoy row {name!r} field 'selection_fraction' must be between 0 "
            f"and 1, got {selection_fraction}.",
        )
        return None
    observed_selection_fraction = counts["pulses"] / scenario_pulses
    if not math.isclose(
        selection_fraction,
        observed_selection_fraction,
        rel_tol=1e-9,
        abs_tol=1e-12,
    ):
        add_issue(
            "INCONSISTENT_DECOY_SELECTION_FRACTION",
            f"Decoy row {name!r} selection_fraction must equal pulses / "
            f"scenario.pulses; expected {observed_selection_fraction}, got "
            f"{selection_fraction}.",
        )
        return None

    if "mean_photon_number" in row:
        supplied_mean = row["mean_photon_number"]
        if not isinstance(supplied_mean, int | float) or isinstance(
            supplied_mean,
            bool,
        ):
            add_issue(
                "INVALID_DECOY_INTENSITY",
                f"Decoy row {name!r} mean_photon_number must be numeric, got "
                f"{supplied_mean!r}.",
            )
            return None
        normalized_mean = float(supplied_mean)
        if not math.isfinite(normalized_mean):
            add_issue(
                "NON_FINITE_DECOY_FIELD",
                f"Decoy row {name!r} mean_photon_number must be finite, got "
                f"{supplied_mean!r}.",
            )
            return None
        if not math.isclose(
            normalized_mean,
            mean_photon_number,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            add_issue(
                "DECOY_INTENSITY_MISMATCH",
                f"Decoy row {name!r} mean_photon_number must match the configured "
                f"value {mean_photon_number}, got {normalized_mean}.",
            )
            return None

    qber_defined = counts["sifted"] > 0
    expected_qber = (
        counts["errors"] / counts["sifted"] if qber_defined else 0.0
    )
    if not math.isclose(
        rates["qber"],
        expected_qber,
        rel_tol=1e-9,
        abs_tol=1e-12,
    ):
        add_issue(
            "INCONSISTENT_DECOY_QBER",
            f"Decoy row {name!r} qber must equal errors / sifted (or 0 with "
            f"no sifted bits); expected {expected_qber}, got {rates['qber']}.",
        )
        return None
    if "qber_defined" in row:
        supplied_qber_defined = row["qber_defined"]
        if not isinstance(supplied_qber_defined, bool):
            add_issue(
                "INVALID_DECOY_QBER_STATUS",
                f"Decoy row {name!r} qber_defined must be boolean, got "
                f"{supplied_qber_defined!r}.",
            )
            return None
        if supplied_qber_defined != qber_defined:
            add_issue(
                "INCONSISTENT_DECOY_QBER_STATUS",
                f"Decoy row {name!r} qber_defined must be true exactly when "
                f"sifted > 0; got qber_defined={supplied_qber_defined!r} and "
                f"sifted={counts['sifted']}.",
            )
            return None

    return _ValidatedIntensityRow(
        name=name,
        mean_photon_number=mean_photon_number,
        pulses=counts["pulses"],
        detected=counts["detected"],
        sifted=counts["sifted"],
        errors=counts["errors"],
        gain=rates["gain"],
        qber=rates["qber"],
        qber_defined=qber_defined,
        selection_fraction=selection_fraction,
    )


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


def _invalid_estimate(
    method: str,
    warnings: list[str],
    *,
    reason_codes: list[str],
    data_status: str = "insufficient_data",
) -> JSONObject:
    return {
        "valid": False,
        "data_status": data_status,
        "method": method,
        "secret_key_rate_bps": 0.0,
        "security_scope": "pedagogical_asymptotic_diagnostic",
        "finite_key": False,
        "composable": False,
        "reason_codes": reason_codes,
        "reasons": warnings,
        "warnings": warnings,
    }
