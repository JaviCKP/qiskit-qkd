"""Derived metric helpers for plot-ready analysis rows."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import TypeAlias

from qiskit_qkd.results import SimulationResult

MetricRowValue: TypeAlias = str | int | float | bool | None
MetricRow: TypeAlias = dict[str, MetricRowValue]


def metric_rows_from_results(
    results: Mapping[str, SimulationResult] | Iterable[SimulationResult],
    *,
    label_key: str = "label",
    qber_abort_threshold: float | None = None,
) -> list[MetricRow]:
    """Flatten simulation results into JSON-safe rows with derived metrics."""

    rows: list[MetricRow] = []
    for label, result in _iter_labeled_results(results):
        legacy_metrics = result.metrics.to_dict()
        row: MetricRow = {
            label_key: label,
            "seed": result.scenario.seed,
            "protocol": result.scenario.protocol.name,
            "channel_kind": result.scenario.channel.kind,
            "source_kind": result.scenario.source.kind,
        }
        row.update(legacy_metrics)
        row["legacy_qber"] = legacy_metrics["qber"]
        row["legacy_abort"] = legacy_metrics["abort"]
        row["abort_is_legacy"] = True
        for key in (
            "corrected_key_length",
            "final_key_length",
            "leak_ec",
            "estimated_qber",
            "residual_mismatches",
        ):
            if key not in result.classical:
                continue
            value = result.classical.get(key)
            if isinstance(value, str | int | float | bool) or value is None:
                row[key] = value
        assessment = _assessment_scalars(result)
        for key, value in assessment.items():
            row.setdefault(key, value)
        # The assessment resolves which QBER evidence is authoritative. Keep
        # the schema-v1 aggregate beside it for consumers auditing old data.
        row["qber"] = (
            assessment.get("qber_value")
            if assessment.get("qber_defined") is True
            else None
        )
        rows.append(row)
    return add_derived_metrics(rows, qber_abort_threshold=qber_abort_threshold)


def add_derived_metrics(
    rows: Iterable[Mapping[str, MetricRowValue]],
    *,
    qber_abort_threshold: float | None = None,
) -> list[MetricRow]:
    """Return copies enriched with diagnostics, never a security assertion.

    ``secure`` remains in the row schema for compatibility but is always false;
    ``secure_is_legacy`` marks that deprecated interpretation explicitly.
    """

    enriched: list[MetricRow] = []
    for row in rows:
        output = dict(row)
        pulses = _number(row.get("pulses"))
        emitted = _number(row.get("emitted"))
        transmitted = _number(row.get("transmitted"))
        detected = _number(row.get("detected"))
        sifted = _number(row.get("sifted"))
        errors = _number(row.get("errors"))
        timing_discards = _number(row.get("timing_discards"))
        corrected_key_length = _number(row.get("corrected_key_length"))
        final_key_length = _number(row.get("final_key_length"))
        qber = (
            None
            if row.get("qber_defined") is False
            else _number(row.get("qber"))
        )
        chsh_s = _number(row.get("chsh_s"))

        _set_if_number(output, "emission_fraction", _ratio(emitted, pulses))
        _set_if_number(output, "transmission_fraction", _ratio(transmitted, emitted))
        _set_if_number(output, "detected_fraction", _ratio(detected, pulses))
        _set_if_number(output, "sifted_fraction", _ratio(sifted, detected))
        _set_if_number(output, "error_fraction", _ratio(errors, sifted))
        _set_if_number(
            output,
            "timing_discard_fraction",
            _ratio(timing_discards, transmitted),
        )
        _set_if_number(
            output,
            "privacy_efficiency",
            _ratio(final_key_length, corrected_key_length),
        )
        if qber_abort_threshold is not None:
            output["qber_margin"] = (
                qber_margin(qber, qber_abort_threshold)
                if qber is not None
                else None
            )
        if chsh_s is not None:
            output["chsh_margin"] = chsh_margin(chsh_s)
        output["key_estimate_available"] = (
            row.get("key_status") == "estimated_key_available"
        )
        # Kept for row-schema compatibility only. A positive asymptotic rate is
        # not, by itself, a finite-key or composable security claim.
        output["secure"] = False
        output["secure_is_legacy"] = True
        enriched.append(output)
    return enriched


def summarize_metric_rows(
    rows: Iterable[Mapping[str, MetricRowValue]],
    *,
    group_by: tuple[str, ...],
    metrics: tuple[str, ...],
) -> list[MetricRow]:
    """Aggregate rows, omitting dispersion for fewer than two observations."""

    groups: dict[tuple[MetricRowValue, ...], list[Mapping[str, MetricRowValue]]] = {}
    for row in rows:
        key = tuple(row.get(name) for name in group_by)
        groups.setdefault(key, []).append(row)

    summary: list[MetricRow] = []
    for key, group_rows in sorted(
        groups.items(),
        key=lambda item: tuple(_sort_token(value) for value in item[0]),
    ):
        output: MetricRow = dict(zip(group_by, key, strict=True))
        output["samples"] = len(group_rows)
        for metric in metrics:
            values = [
                value
                for value in (_number(row.get(metric)) for row in group_rows)
                if value is not None
            ]
            output[f"{metric}_finite_count"] = len(values)
            if not values:
                continue
            mean = math.fsum(values) / len(values)
            sorted_values = sorted(values)
            output[f"{metric}_mean"] = mean
            output[f"{metric}_min"] = sorted_values[0]
            output[f"{metric}_max"] = sorted_values[-1]
            if len(values) >= 2:
                variance = (
                    math.fsum((value - mean) ** 2 for value in values)
                    / len(values)
                )
                output[f"{metric}_std"] = math.sqrt(variance)
                output[f"{metric}_p05"] = _percentile(sorted_values, 0.05)
                output[f"{metric}_p95"] = _percentile(sorted_values, 0.95)
        legacy_abort_values = [
            value
            for value in (_legacy_abort_value(row) for row in group_rows)
            if value is not None
        ]
        if legacy_abort_values:
            legacy_abort_fraction = sum(legacy_abort_values) / len(
                legacy_abort_values,
            )
            output["legacy_abort_count"] = len(legacy_abort_values)
            output["legacy_abort_fraction"] = legacy_abort_fraction
            # Compatibility alias for callers of the pre-assessment API.
            output["abort_fraction"] = legacy_abort_fraction
            output["abort_fraction_is_legacy"] = True
        if any("threshold_exceeded" in row for row in group_rows):
            threshold_decisions = [
                value
                for row in group_rows
                if isinstance((value := row.get("threshold_exceeded")), bool)
            ]
            output["threshold_decision_count"] = len(threshold_decisions)
            output["threshold_decision_fraction"] = (
                sum(threshold_decisions) / len(threshold_decisions)
                if threshold_decisions
                else None
            )
        if any("secure" in row for row in group_rows):
            legacy_true_fraction = sum(
                int(row.get("secure") is True)
                for row in group_rows
            ) / len(group_rows)
            output["secure_fraction"] = 0.0
            output["secure_fraction_is_legacy"] = True
            output["legacy_secure_input_true_fraction"] = legacy_true_fraction
        if any("key_estimate_available" in row for row in group_rows):
            output["key_estimate_available_fraction"] = sum(
                int(row.get("key_estimate_available") is True)
                for row in group_rows
            ) / len(group_rows)
        summary.append(output)
    return summary


def secure_distance_limit(
    rows: Iterable[Mapping[str, MetricRowValue]],
    *,
    distance_key: str = "distance_km",
    rate_key: str = "secret_key_rate_bps",
) -> float | None:
    """Return the largest sampled distance with a consistent key estimate.

    The legacy function name is retained for API compatibility. Rows must now
    explicitly report ``key_status='estimated_key_available'`` and
    ``rate_estimate_status='available'``; a positive schema-v1 rate and
    ``abort=False`` alone are deliberately insufficient. The result remains a
    grid-dependent pedagogical diagnostic, not a finite-key or composable
    secure-distance claim.
    """

    distances: list[float] = []
    for row in rows:
        if row.get("key_status") != "estimated_key_available":
            continue
        if row.get("rate_estimate_status") != "available":
            continue
        if row.get("qber_defined") is False:
            continue
        if row.get("threshold_exceeded") is True:
            continue
        if row.get("verification_status") == "failed":
            continue
        distance = _number(row.get(distance_key))
        rate = _number(row.get(rate_key))
        if distance is not None and rate is not None and rate > 0.0:
            distances.append(distance)
    return max(distances) if distances else None


def qber_margin(qber: float, threshold: float) -> float:
    """Return positive margin below a configured QBER abort threshold."""

    return float(threshold) - float(qber)


def chsh_margin(chsh_s: float) -> float:
    """Return positive margin above the classical CHSH bound S=2."""

    return float(chsh_s) - 2.0


def _iter_labeled_results(
    results: Mapping[str, SimulationResult] | Iterable[SimulationResult],
) -> Iterable[tuple[str, SimulationResult]]:
    if isinstance(results, Mapping):
        yield from results.items()
        return
    for index, result in enumerate(results):
        yield str(index), result


def _assessment_scalars(result: SimulationResult) -> MetricRow:
    """Return scalar assessment fields without replacing established columns."""

    assessment = getattr(result, "assessment", None)
    if assessment is None:
        return {}
    if isinstance(assessment, Mapping):
        payload = assessment
    else:
        to_dict = getattr(assessment, "to_dict", None)
        if not callable(to_dict):
            return {}
        payload = to_dict()
        if not isinstance(payload, Mapping):
            return {}
    return {
        key: value
        for key, value in payload.items()
        if isinstance(key, str)
        and (isinstance(value, str | int | float | bool) or value is None)
    }


def _sort_token(value: MetricRowValue) -> tuple[int, float | str]:
    """Order mixed-type group keys: numbers first, then strings, then None."""

    if isinstance(value, int | float) and not isinstance(value, bool):
        return (0, float(value))
    if value is None:
        return (2, "")
    return (1, str(value))


def _legacy_abort_value(row: Mapping[str, MetricRowValue]) -> bool | None:
    value = row.get("legacy_abort")
    if not isinstance(value, bool):
        value = row.get("abort")
    return value if isinstance(value, bool) else None


def _number(value: MetricRowValue) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, int | float):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0.0:
        return None
    return numerator / denominator


def _set_if_number(row: MetricRow, key: str, value: float | None) -> None:
    if value is not None:
        row[key] = value


def _percentile(sorted_values: list[float], quantile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = quantile * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
