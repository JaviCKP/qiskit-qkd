"""Single-photon source models for QKD event simulations."""

from __future__ import annotations

import math
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
    require_non_negative_number,
    require_probability,
)
from qiskit_qkd.config import DecoyIntensity, SourceConfig

_POISSON_INVERSION_MAX_MEAN = 30.0
_MAX_POISSON_MEAN = 1_000_000_000_000.0


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


@dataclass(frozen=True, slots=True)
class WeakCoherentDecoySource:
    """Phase-randomized weak coherent source with decoy intensity classes."""

    intensities: tuple[DecoyIntensity, ...]

    def __post_init__(self) -> None:
        if not self.intensities:
            raise ValueError("intensities must contain at least one decoy class")
        object.__setattr__(
            self,
            "intensities",
            tuple(self.intensities),
        )

    def emit(self, *, rng: random.Random, time_s: float) -> EmissionEvent:
        """Sample an intensity class and Poisson photon number."""

        intensity = self._sample_intensity(rng)
        photon_number = _sample_poisson(rng, intensity.mean_photon_number)
        return EmissionEvent(
            emitted=photon_number > 0,
            photon_number=photon_number,
            time_s=time_s,
            intensity_class=intensity.name,
        )

    def _sample_intensity(self, rng: random.Random) -> DecoyIntensity:
        sample = rng.random()
        cumulative = 0.0
        for intensity in self.intensities:
            cumulative += intensity.selection_probability
            if sample < cumulative:
                return intensity
        return self.intensities[-1]


@dataclass(frozen=True, slots=True)
class EntangledPairSource:
    """Bernoulli source that emits one entangled photon pair per clock slot."""

    emission_probability: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "emission_probability",
            require_probability("emission_probability", self.emission_probability),
        )

    def emit(self, *, rng: random.Random, time_s: float) -> EmissionEvent:
        """Sample whether this slot emits a two-photon entangled pair."""

        emitted = rng.random() < self.emission_probability
        return EmissionEvent(
            emitted=emitted,
            photon_number=2 if emitted else 0,
            time_s=time_s,
            intensity_class="entangled_pair",
        )


def _sample_poisson(rng: random.Random, mean_photon_number: float) -> int:
    mean = require_non_negative_number(
        "mean_photon_number",
        mean_photon_number,
    )
    if mean > _MAX_POISSON_MEAN:
        raise ValueError(
            "mean_photon_number exceeds the Poisson sampling limit: "
            f"got {mean!r}, maximum {_MAX_POISSON_MEAN!r}; reduce the source mean",
        )
    if mean == 0.0:
        return 0
    if mean < _POISSON_INVERSION_MAX_MEAN:
        return _sample_poisson_inversion(rng, mean)
    return _sample_poisson_ptrs(rng, mean)


def _sample_poisson_inversion(rng: random.Random, mean: float) -> int:
    """Keep the historical RNG sequence for ordinary weak-coherent means."""

    threshold = math.exp(-mean)
    product = 1.0
    photons = 0
    while product > threshold:
        photons += 1
        product *= rng.random()
    return photons - 1


def _sample_poisson_ptrs(rng: random.Random, mean: float) -> int:
    """Sample large means with Hoermann's transformed-rejection method."""

    sqrt_mean = math.sqrt(mean)
    log_mean = math.log(mean)
    b = 0.931 + 2.53 * sqrt_mean
    a = -0.059 + 0.02483 * b
    inverse_alpha = 1.1239 + 1.1328 / (b - 3.4)
    squeeze = 0.9277 - 3.6224 / (b - 2.0)
    while True:
        centered_uniform = rng.random() - 0.5
        acceptance_uniform = rng.random()
        distance_from_edge = 0.5 - abs(centered_uniform)
        if distance_from_edge <= 0.0:
            continue
        candidate = math.floor(
            (2.0 * a / distance_from_edge + b) * centered_uniform
            + mean
            + 0.43,
        )
        if distance_from_edge >= 0.07 and acceptance_uniform <= squeeze:
            return candidate
        if candidate < 0 or (
            distance_from_edge < 0.013
            and acceptance_uniform > distance_from_edge
        ):
            continue
        if acceptance_uniform == 0.0:
            return candidate
        acceptance_log = (
            math.log(acceptance_uniform)
            + math.log(inverse_alpha)
            - math.log(a / (distance_from_edge * distance_from_edge) + b)
        )
        poisson_log_mass = (
            -mean + candidate * log_mean - math.lgamma(candidate + 1.0)
        )
        if acceptance_log <= poisson_log_mass:
            return candidate


def source_from_config(
    config: SourceConfig,
) -> IdealSinglePhotonSource | WeakCoherentDecoySource | EntangledPairSource:
    """Build a concrete source model from validated scenario configuration."""

    kind = config.kind.lower()
    if kind in {"ideal", "ideal_single_photon", "single_photon"}:
        return IdealSinglePhotonSource(
            emission_probability=config.emission_probability,
        )
    if kind in {"weak_coherent", "decoy_weak_coherent"}:
        intensities = config.decoy_intensities
        if not intensities:
            if config.mean_photon_number is None:
                raise ValueError(
                    "weak_coherent sources require mean_photon_number when "
                    "decoy_intensities is empty",
                )
            intensities = (
                DecoyIntensity(
                    name="signal",
                    mean_photon_number=config.mean_photon_number,
                    selection_probability=1.0,
                ),
            )
        return WeakCoherentDecoySource(intensities=intensities)
    if kind in {"entangled_pair", "bell_pair", "e91"}:
        return EntangledPairSource(
            emission_probability=config.emission_probability,
        )
    raise ValueError(f"Unsupported source kind: {config.kind!r}")
