"""Reusable physical-round preparation for QKD channel simulations."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol, cast

from qiskit_qkd._validation import (
    require_non_empty_str,
    require_non_negative_int,
    require_probability,
)
from qiskit_qkd.channels.impairments import pdl_transmittance_factor
from qiskit_qkd.config import Scenario
from qiskit_qkd.sources import EmissionEvent
from qiskit_qkd.timing import (
    TimingContext,
    assign_timing,
    timing_context_from_scenario,
)


class SourceLike(Protocol):
    def emit(self, *, rng: random.Random, time_s: float) -> EmissionEvent:
        """Sample an emission for one clock slot."""


class ChannelLike(Protocol):
    def transmit(self, rng: random.Random) -> bool:
        """Sample whether an emitted photon survives the channel."""


class TransmittanceChannelLike(Protocol):
    def transmittance(self) -> float:
        """Return the current channel transmittance."""


class SampledTransmittanceChannelLike(TransmittanceChannelLike, Protocol):
    def sample_transmittance(self, rng: random.Random) -> float:
        """Sample the instantaneous channel transmittance."""


@dataclass(frozen=True, slots=True)
class PreparedState:
    """Logical and physical state emitted by Alice for one BB84 pulse.

    ``alice_bit`` is the bit Alice records for sifting, while ``prepared_bit``
    is the state that actually enters the optical channel.  Keeping both values
    prevents a preparation error from being sampled again after an Eve attack.
    """

    alice_bit: int
    alice_basis: str
    prepared_bit: int
    preparation_error: bool = False
    preparation_error_applied: bool = False

    def __post_init__(self) -> None:
        if self.alice_bit not in {0, 1} or isinstance(self.alice_bit, bool):
            raise ValueError("alice_bit must be 0 or 1")
        if self.prepared_bit not in {0, 1} or isinstance(self.prepared_bit, bool):
            raise ValueError("prepared_bit must be 0 or 1")
        require_non_empty_str("alice_basis", self.alice_basis)
        if not isinstance(self.preparation_error, bool):
            raise TypeError("preparation_error must be a bool")
        if not isinstance(self.preparation_error_applied, bool):
            raise TypeError("preparation_error_applied must be a bool")

    @classmethod
    def sample(
        cls,
        *,
        alice_bit: int,
        alice_basis: str,
        preparation_error_probability: float,
        rng: random.Random,
    ) -> PreparedState:
        """Sample source preparation once, before any adversarial operation."""

        probability = require_probability(
            "preparation_error_probability",
            preparation_error_probability,
        )
        error = probability > 0.0 and rng.random() < probability
        return cls(
            alice_bit=alice_bit,
            alice_basis=alice_basis,
            prepared_bit=1 - alice_bit if error else alice_bit,
            preparation_error=error,
        )

    @property
    def bit(self) -> int:
        """Alias for the physical bit, useful for attack/circuit adapters."""

        return self.prepared_bit


@dataclass(frozen=True, slots=True)
class PhysicalRound:
    """Source, channel, and timing outcome for one attempted clock slot."""

    index: int
    time_s: float
    time_slot: int
    emission_time_s: float
    expected_arrival_time_s: float
    arrival_time_s: float | None
    bob_gate_start_s: float
    bob_gate_end_s: float
    signal_assigned_slot: int | None
    timing_status: str
    emitted: bool
    photon_number: int
    surviving_photon_number: int
    intensity_class: str | None
    transmitted: bool

    @property
    def assigned_signal_present(self) -> bool:
        return self.signal_assigned_slot is not None


def prepare_physical_round(
    *,
    index: int,
    scenario: Scenario,
    source: SourceLike,
    channel: ChannelLike,
    rng: random.Random,
    alice_bit: int | None = None,
    alice_basis: str | None = None,
    timing_context: TimingContext | None = None,
) -> PhysicalRound:
    """Sample source emission, channel transmission, and Bob timing metadata."""

    index = require_non_negative_int("index", index)
    context = timing_context or timing_context_from_scenario(scenario)
    slot_period_s = context.slot_period_s
    emission_time_s = index * slot_period_s
    emission = source.emit(rng=rng, time_s=emission_time_s)
    surviving_photon_number = sample_surviving_photons(
        channel,
        rng,
        emission.photon_number,
        scenario=scenario,
        alice_bit=alice_bit,
        alice_basis=alice_basis,
    )
    return physical_round_from_emission(
        index=index,
        scenario=scenario,
        emission=emission,
        surviving_photon_number=surviving_photon_number,
        rng=rng,
        timing_context=context,
    )


def physical_round_from_emission(
    *,
    index: int,
    scenario: Scenario,
    emission: EmissionEvent,
    surviving_photon_number: int,
    rng: random.Random,
    timing_context: TimingContext | None = None,
) -> PhysicalRound:
    """Attach channel/timing metadata to an already sampled emission.

    This seam lets protocol runners place an Eve operation between source
    preparation and channel loss without duplicating timing logic.
    """

    index = require_non_negative_int("index", index)
    surviving_photon_number = require_non_negative_int(
        "surviving_photon_number",
        surviving_photon_number,
    )
    if surviving_photon_number > emission.photon_number:
        raise ValueError(
            "surviving_photon_number cannot exceed emitted photon_number",
        )
    context = timing_context or timing_context_from_scenario(scenario)
    transmitted = surviving_photon_number > 0
    timing = assign_timing(
        time_slot=index,
        pulses=scenario.pulses,
        clock_rate_hz=scenario.clock_rate_hz,
        gate_width_s=scenario.detector.gate_width_s,
        timing=context.timing,
        transmitted=transmitted,
        rng=rng,
        context=context,
    )
    return PhysicalRound(
        index=index,
        time_s=timing.emission_time_s,
        time_slot=timing.time_slot,
        emission_time_s=timing.emission_time_s,
        expected_arrival_time_s=timing.expected_arrival_time_s,
        arrival_time_s=timing.arrival_time_s,
        bob_gate_start_s=timing.bob_gate_start_s,
        bob_gate_end_s=timing.bob_gate_end_s,
        signal_assigned_slot=timing.signal_assigned_slot,
        timing_status=timing.timing_status,
        emitted=emission.emitted,
        photon_number=emission.photon_number,
        surviving_photon_number=surviving_photon_number,
        intensity_class=emission.intensity_class,
        transmitted=transmitted,
    )


def sample_surviving_photons(
    channel: ChannelLike,
    rng: random.Random,
    photon_number: int,
    *,
    scenario: Scenario | None = None,
    alice_bit: int | None = None,
    alice_basis: str | None = None,
) -> int:
    """Sample photons surviving a channel segment.

    Publicly exposing this operation keeps the default post-loss model intact
    while allowing a protocol to place Eve before the segment.
    """

    return _surviving_photon_count(
        channel,
        rng,
        photon_number,
        scenario=scenario,
        alice_bit=alice_bit,
        alice_basis=alice_basis,
    )


def _surviving_photon_count(
    channel: ChannelLike,
    rng: random.Random,
    photon_number: int,
    *,
    scenario: Scenario | None = None,
    alice_bit: int | None = None,
    alice_basis: str | None = None,
) -> int:
    photon_number = require_non_negative_int("photon_number", photon_number)
    if photon_number == 0:
        return 0
    if not hasattr(channel, "transmittance"):
        return sum(int(channel.transmit(rng)) for _ in range(photon_number))
    eta = _sample_channel_transmittance(channel, rng)
    if scenario is not None:
        eta *= pdl_transmittance_factor(
            scenario.channel,
            alice_bit=alice_bit,
            alice_basis=alice_basis,
        )
        eta = min(1.0, max(0.0, eta))
    return sum(int(rng.random() < eta) for _ in range(photon_number))


def _sample_channel_transmittance(channel: ChannelLike, rng: random.Random) -> float:
    if hasattr(channel, "sample_transmittance"):
        sampled_channel = cast(SampledTransmittanceChannelLike, channel)
        return require_probability(
            "channel.sample_transmittance",
            sampled_channel.sample_transmittance(rng),
        )
    transmittance_channel = cast(TransmittanceChannelLike, channel)
    return require_probability(
        "channel.transmittance",
        transmittance_channel.transmittance(),
    )
