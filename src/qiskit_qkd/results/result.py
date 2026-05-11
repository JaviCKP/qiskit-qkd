"""Serializable simulation result containers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from qiskit_qkd._json import (
    JSONObject,
    dumps_pretty,
    loads_object,
    normalize_json_object,
)
from qiskit_qkd._validation import reject_unknown_fields, require_bool
from qiskit_qkd._version import __version__
from qiskit_qkd.config import Scenario

from .event import Event
from .metrics import Metrics

RESULT_SCHEMA_VERSION = 1


def default_provenance(scenario: Scenario) -> JSONObject:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "library_version": __version__,
        "seed": scenario.seed,
        "scenario_digest": scenario.digest(),
        "rng": "python.random.Random",
    }


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Scenario, metrics, provenance, and sampled events from one run."""

    scenario: Scenario
    metrics: Metrics
    provenance: JSONObject = field(default_factory=dict)
    qiskit: JSONObject = field(default_factory=dict)
    library_version: str = __version__
    event_sample: tuple[Event, ...] = field(default_factory=tuple)
    aggregated: bool = True

    def __post_init__(self) -> None:
        if self.metrics.pulses != self.scenario.pulses:
            raise ValueError("metrics.pulses must match scenario.pulses")
        merged_provenance = default_provenance(self.scenario)
        merged_provenance.update(
            normalize_json_object(self.provenance, path="provenance"),
        )
        object.__setattr__(self, "provenance", merged_provenance)
        object.__setattr__(
            self,
            "qiskit",
            normalize_json_object(self.qiskit, path="qiskit"),
        )
        object.__setattr__(self, "library_version", str(self.library_version))
        object.__setattr__(self, "event_sample", tuple(self.event_sample))
        object.__setattr__(
            self,
            "aggregated",
            require_bool("aggregated", self.aggregated),
        )
        if (
            not self.scenario.store_full_event_log
            and len(self.event_sample) > self.scenario.event_sample_size
        ):
            raise ValueError("event_sample exceeds scenario.event_sample_size")

    def to_dict(self) -> JSONObject:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "library_version": self.library_version,
            "scenario": self.scenario.to_dict(),
            "metrics": self.metrics.to_dict(),
            "provenance": self.provenance,
            "qiskit": self.qiskit,
            "event_sample": [event.to_dict() for event in self.event_sample],
            "aggregated": self.aggregated,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "SimulationResult",
            data,
            {
                "schema_version",
                "library_version",
                "scenario",
                "metrics",
                "provenance",
                "qiskit",
                "event_sample",
                "aggregated",
            },
        )
        schema_version = data.get("schema_version", RESULT_SCHEMA_VERSION)
        if schema_version != RESULT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported result schema_version: {schema_version}")
        return cls(
            scenario=Scenario.from_dict(data["scenario"]),
            metrics=Metrics.from_dict(data["metrics"]),
            provenance=data.get("provenance", {}),
            qiskit=data.get("qiskit", {}),
            library_version=data.get("library_version", __version__),
            event_sample=tuple(
                Event.from_dict(event_data)
                for event_data in data.get("event_sample", [])
            ),
            aggregated=data.get("aggregated", True),
        )

    def to_json(self) -> str:
        return dumps_pretty(self.to_dict())

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(loads_object(payload))

    def summary(self) -> JSONObject:
        return {
            "library_version": self.library_version,
            "seed": self.scenario.seed,
            "scenario_digest": self.scenario.digest(),
            "metrics": self.metrics.to_dict(),
            "event_sample_size": len(self.event_sample),
            "aggregated": self.aggregated,
        }
