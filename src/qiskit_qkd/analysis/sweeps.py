"""Parameter sweep helpers with JSON-safe outputs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from typing import Any, Protocol

from qiskit_qkd.config import Scenario

BackendFactory = Callable[[Scenario], Any]


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
) -> list[dict[str, float | int | bool]]:
    """Run BB84 for each distance and return JSON-safe metric rows."""

    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    rows: list[dict[str, float | int | bool]] = []
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
