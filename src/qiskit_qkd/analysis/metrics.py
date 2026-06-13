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
        row: MetricRow = {
            label_key: label,
            "seed": result.scenario.seed,
            "protocol": result.scenario.protocol.name,
            "channel_kind": result.scenario.channel.kind,
            "source_kind": result.scenario.source.kind,
        }
        row.update(result.metrics.to_dict())
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
        rows.append(row)
    return add_derived_metrics(rows, qber_abort_threshold=qber_abort_threshold)


def add_derived_metrics(
    rows: Iterable[Mapping[str, MetricRowValue]],
    *,
    qber_abort_threshold: float | None = None,
) -> list[MetricRow]:
    """Return copies of rows enriched with common QKD comparison metrics."""

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
        qber = _number(row.get("qber"))
        secret_key_rate_bps = _number(row.get("secret_key_rate_bps"))
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
        if qber_abort_threshold is not None and qber is not None:
            output["qber_margin"] = qber_margin(qber, qber_abort_threshold)
        if chsh_s is not None:
            output["chsh_margin"] = chsh_margin(chsh_s)
        if secret_key_rate_bps is not None:
            output["secure"] = (
                secret_key_rate_bps > 0.0
                and row.get("abort") is not True
                and (
                    qber_abort_threshold is None
                    or qber is None
                    or qber <= qber_abort_threshold
                )
            )
        enriched.append(output)
    return enriched


def summarize_metric_rows(
    rows: Iterable[Mapping[str, MetricRowValue]],
    *,
    group_by: tuple[str, ...],
    metrics: tuple[str, ...],
) -> list[MetricRow]:
    """Aggregate repeated metric rows into mean/std/min/max summary rows."""

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
            if not values:
                continue
            mean = sum(values) / len(values)
            variance = sum((value - mean) ** 2 for value in values) / len(values)
            sorted_values = sorted(values)
            output[f"{metric}_mean"] = mean
            output[f"{metric}_std"] = math.sqrt(variance)
            output[f"{metric}_min"] = sorted_values[0]
            output[f"{metric}_max"] = sorted_values[-1]
            output[f"{metric}_p05"] = _percentile(sorted_values, 0.05)
            output[f"{metric}_p95"] = _percentile(sorted_values, 0.95)
        if any("abort" in row for row in group_rows):
            output["abort_fraction"] = sum(
                int(row.get("abort") is True)
                for row in group_rows
            ) / len(group_rows)
        if any("secure" in row for row in group_rows):
            output["secure_fraction"] = sum(
                int(row.get("secure") is True)
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
    """Return the largest distance with a positive non-aborted secret rate."""

    distances: list[float] = []
    for row in rows:
        if row.get("abort") is True:
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


def _sort_token(value: MetricRowValue) -> tuple[int, float | str]:
    """Order mixed-type group keys: numbers first, then strings, then None."""

    if isinstance(value, int | float) and not isinstance(value, bool):
        return (0, float(value))
    if value is None:
        return (2, "")
    return (1, str(value))


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
