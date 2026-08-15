"""Reusable physical-round preparation for QKD channel simulations."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol, cast

from qiskit_qkd._validation import (
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
    surviving_photon_number = _surviving_photon_count(
        channel,
        rng,
        emission.photon_number,
        scenario=scenario,
        alice_bit=alice_bit,
        alice_basis=alice_basis,
    )
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
