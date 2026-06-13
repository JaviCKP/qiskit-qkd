"""Source-state characterization helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import require_non_negative_number
from qiskit_qkd.config import DecoyIntensity, Scenario
from qiskit_qkd.temporal import ParameterResolver


@dataclass(frozen=True, slots=True)
class DecoyProbabilityState:
    """Analytical Poisson probabilities for one decoy intensity."""

    name: str
    mean_photon_number: float
    selection_probability: float
    p_zero: float
    p_one: float
    p_multi: float
    multi_photon_fraction_given_emission: float

    def to_dict(self) -> JSONObject:
        return {
            "name": self.name,
            "mean_photon_number": self.mean_photon_number,
            "selection_probability": self.selection_probability,
            "p_zero": self.p_zero,
            "p_one": self.p_one,
            "p_multi": self.p_multi,
            "multi_photon_fraction_given_emission": (
                self.multi_photon_fraction_given_emission
            ),
        }


@dataclass(frozen=True, slots=True)
class SourceState:
    """Analytical source state for the configured emission model."""

    time_s: float
    source_kind: str
    emission_probability: float
    preparation_error_probability: float
    mean_photon_number: float | None
    decoy_probabilities: tuple[DecoyProbabilityState, ...]
    mean_photon_rate_hz: float
    pair_rate_hz: float | None

    def to_dict(self) -> JSONObject:
        return {
            "time_s": self.time_s,
            "source_kind": self.source_kind,
            "emission_probability": self.emission_probability,
            "preparation_error_probability": self.preparation_error_probability,
            "mean_photon_number": self.mean_photon_number,
            "decoy_probabilities": [
                state.to_dict() for state in self.decoy_probabilities
            ],
            "mean_photon_rate_hz": self.mean_photon_rate_hz,
            "pair_rate_hz": self.pair_rate_hz,
        }


def source_state_from_scenario(
    scenario: Scenario,
    *,
    time_s: float = 0.0,
    resolver: ParameterResolver | None = None,
) -> SourceState:
    """Return the analytical source state at ``time_s``."""

    time = require_non_negative_number("time_s", time_s)
    active_resolver = resolver or ParameterResolver()
    effective = active_resolver.scenario_at(scenario, time_s=time)
    return _source_state_from_effective(effective, time_s=time)


def _source_state_from_effective(scenario: Scenario, *, time_s: float) -> SourceState:
    source = scenario.source
    intensities = _intensities_for(source.decoy_intensities, source.mean_photon_number)
    decoy_states = tuple(
        _decoy_probability_state(intensity) for intensity in intensities
    )
    weighted_mean = sum(
        state.selection_probability * state.mean_photon_number
        for state in decoy_states
    )
    if not decoy_states and source.kind in {
        "ideal",
        "ideal_single_photon",
        "single_photon",
    }:
        weighted_mean = source.emission_probability

    pair_rate_hz: float | None = None
    if source.kind in {"entangled_pair", "bell_pair", "e91"}:
        pair_rate_hz = scenario.clock_rate_hz * source.emission_probability
        weighted_mean = 2.0 * source.emission_probability

    return SourceState(
        time_s=time_s,
        source_kind=source.kind,
        emission_probability=source.emission_probability,
        preparation_error_probability=source.preparation_error_probability,
        mean_photon_number=source.mean_photon_number,
        decoy_probabilities=decoy_states,
        mean_photon_rate_hz=scenario.clock_rate_hz * weighted_mean,
        pair_rate_hz=pair_rate_hz,
    )


def _intensities_for(
    decoy_intensities: tuple[DecoyIntensity, ...],
    mean_photon_number: float | None,
) -> tuple[DecoyIntensity, ...]:
    if decoy_intensities:
        return decoy_intensities
    if mean_photon_number is None:
        return ()
    return (
        DecoyIntensity(
            name="signal",
            mean_photon_number=mean_photon_number,
            selection_probability=1.0,
        ),
    )


def _decoy_probability_state(intensity: DecoyIntensity) -> DecoyProbabilityState:
    p_zero = math.exp(-intensity.mean_photon_number)
    p_one = intensity.mean_photon_number * p_zero
    p_multi = max(0.0, 1.0 - p_zero - p_one)
    emission_probability = 1.0 - p_zero
    conditioned = 0.0 if emission_probability == 0.0 else p_multi / emission_probability
    return DecoyProbabilityState(
        name=intensity.name,
        mean_photon_number=intensity.mean_photon_number,
        selection_probability=intensity.selection_probability,
        p_zero=p_zero,
        p_one=p_one,
        p_multi=p_multi,
        multi_photon_fraction_given_emission=conditioned,
    )
