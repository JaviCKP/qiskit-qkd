"""Parameter sweep helpers with JSON-safe outputs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any, Protocol

from qiskit_qkd.analysis.metrics import metric_rows_from_results
from qiskit_qkd.config import Scenario
from qiskit_qkd.config.dynamics import validate_parameter_target
from qiskit_qkd.temporal import ParameterResolver

BackendFactory = Callable[[Scenario], Any]
SweepValue = float | int | bool | None


class BB84Runner(Protocol):
    def run(self, scenario: Scenario, backend: Any | None = None) -> Any:
        """Run a BB84-compatible protocol and return a result object."""
        ...


def sweep_bb84_distance(
    protocol: BB84Runner,
    scenario: Scenario,
    distances_km: Iterable[float],
    *,
    repeats: int = 1,
    backend_factory: BackendFactory | None = None,
) -> list[dict[str, SweepValue]]:
    """Run BB84 for each distance and return JSON-safe metric rows."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    rows: list[dict[str, SweepValue]] = []
    for distance_km in distances_km:
        for repeat in range(repeats):
            run_scenario = replace(
                scenario,
                seed=scenario.seed + repeat,
                channel=replace(scenario.channel, distance_km=float(distance_km)),
            )
            backend = (
                None
                if backend_factory is None
                else backend_factory(run_scenario)
            )
            result = protocol.run(run_scenario, backend=backend)
            metrics = result.metrics
            rows.append(
                {
                    "distance_km": float(distance_km),
                    "repeat": repeat,
                    "seed": run_scenario.seed,
                    "loss_db": metrics.loss_db,
                    "qber": metrics.qber,
                    "emitted": metrics.emitted,
                    "transmitted": metrics.transmitted,
                    "detected": metrics.detected,
                    "sifted": metrics.sifted,
                    "errors": metrics.errors,
                    "gain": metrics.gain,
                    "raw_detection_rate_hz": metrics.raw_detection_rate_hz,
                    "sifted_key_rate_bps": metrics.sifted_key_rate_bps,
                    "secret_key_rate_bps": metrics.secret_key_rate_bps,
                    "abort": metrics.abort,
                },
            )
    return rows


def sweep_bb84_time(
    protocol: BB84Runner,
    scenario: Scenario,
    time_points_s: Iterable[float],
    *,
    repeats: int = 1,
    backend_factory: BackendFactory | None = None,
    resolver: ParameterResolver | None = None,
) -> list[dict[str, SweepValue]]:
    """Run BB84 at selected times using the scenario's dynamic schedules."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    active_resolver = resolver or ParameterResolver()
    rows: list[dict[str, SweepValue]] = []
    for time_index, time_s in enumerate(time_points_s):
        effective = active_resolver.scenario_at(scenario, time_s=float(time_s))
        dynamic_values = active_resolver.parameter_values(
            scenario,
            time_s=float(time_s),
        )
        for repeat in range(repeats):
            run_scenario = replace(
                effective,
                seed=scenario.seed + time_index * repeats + repeat,
            )
            backend = (
                None
                if backend_factory is None
                else backend_factory(run_scenario)
            )
            result = protocol.run(run_scenario, backend=backend)
            metrics = result.metrics
            row: dict[str, SweepValue] = {
                "time_s": float(time_s),
                "repeat": repeat,
                "seed": run_scenario.seed,
                "loss_db": metrics.loss_db,
                "qber": metrics.qber,
                "emitted": metrics.emitted,
                "transmitted": metrics.transmitted,
                "detected": metrics.detected,
                "sifted": metrics.sifted,
                "errors": metrics.errors,
                "gain": metrics.gain,
                "raw_detection_rate_hz": metrics.raw_detection_rate_hz,
                "sifted_key_rate_bps": metrics.sifted_key_rate_bps,
                "secret_key_rate_bps": metrics.secret_key_rate_bps,
                "abort": metrics.abort,
            }
            row.update(dynamic_values)
            rows.append(row)
    return rows


def sweep_scenario_parameter(
    protocol: BB84Runner,
    scenario: Scenario,
    target: str,
    values: Iterable[SweepValue],
    *,
    repeats: int = 1,
    backend_factory: BackendFactory | None = None,
) -> list[dict[str, SweepValue]]:
    """Run a protocol while sweeping any registered scenario target."""

    normalized_target = validate_parameter_target(target)
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    rows: list[dict[str, SweepValue]] = []
    for value_index, value in enumerate(values):
        for repeat in range(repeats):
            run_scenario = _replace_target(
                replace(scenario, seed=scenario.seed + value_index * repeats + repeat),
                normalized_target,
                value,
            )
            backend = (
                None
                if backend_factory is None
                else backend_factory(run_scenario)
            )
            result = protocol.run(run_scenario, backend=backend)
            row = metric_rows_from_results(
                [result],
                label_key="run",
                qber_abort_threshold=run_scenario.post_processing.qber_abort_threshold,
            )[0]
            row["target"] = normalized_target
            row[normalized_target] = value
            row["repeat"] = repeat
            rows.append(row)
    return rows


def _replace_target(scenario: Scenario, target: str, value: Any) -> Scenario:
    section, field = target.split(".")
    if section == "scenario":
        return replace(scenario, **{field: value})
    section_config = getattr(scenario, section)
    return replace(scenario, **{section: replace(section_config, **{field: value})})
