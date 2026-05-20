"""Single-photon source models for QKD event simulations."""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    reject_unknown_fields,
    require_bool,
    require_finite_number,
    require_non_empty_str,
    require_non_negative_int,
    require_probability,
)
from qiskit_qkd.config import SourceConfig


def _validate_optional_str(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(name, value)


@dataclass(frozen=True, slots=True)
class EmissionEvent:
    """Source outcome for one attempted QKD clock slot."""

    emitted: bool
    photon_number: int
    time_s: float
    intensity_class: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "emitted", require_bool("emitted", self.emitted))
        object.__setattr__(
            self,
            "photon_number",
            require_non_negative_int("photon_number", self.photon_number),
        )
        object.__setattr__(self, "time_s", require_finite_number("time_s", self.time_s))
        if self.time_s < 0.0:
            raise ValueError("time_s must be non-negative")
        object.__setattr__(
            self,
            "intensity_class",
            _validate_optional_str("intensity_class", self.intensity_class),
        )
        if self.emitted and self.photon_number == 0:
            raise ValueError("emitted events must contain at least one photon")
        if not self.emitted and self.photon_number != 0:
            raise ValueError("non-emitted events must contain zero photons")

    def to_dict(self) -> JSONObject:
        return {
            "emitted": self.emitted,
            "photon_number": self.photon_number,
            "time_s": self.time_s,
            "intensity_class": self.intensity_class,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "EmissionEvent",
            data,
            {"emitted", "photon_number", "time_s", "intensity_class"},
        )
        return cls(
            emitted=data["emitted"],
            photon_number=data["photon_number"],
            time_s=data["time_s"],
            intensity_class=data.get("intensity_class"),
        )


@dataclass(frozen=True, slots=True)
class IdealSinglePhotonSource:
    """Bernoulli source that emits at most one photon per clock slot."""

    emission_probability: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "emission_probability",
            require_probability("emission_probability", self.emission_probability),
        )

    def emit(self, *, rng: random.Random, time_s: float) -> EmissionEvent:
        """Sample whether this slot emits one photon."""

        emitted = rng.random() < self.emission_probability
        return EmissionEvent(
            emitted=emitted,
            photon_number=int(emitted),
            time_s=time_s,
        )


def source_from_config(config: SourceConfig) -> IdealSinglePhotonSource:
    """Build a concrete source model from validated scenario configuration."""

    kind = config.kind.lower()
    if kind in {"ideal", "ideal_single_photon", "single_photon"}:
        return IdealSinglePhotonSource(
            emission_probability=config.emission_probability,
        )
    raise ValueError(f"Unsupported source kind: {config.kind!r}")
