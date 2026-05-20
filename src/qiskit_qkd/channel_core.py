"""Reusable physical-round preparation for QKD channel simulations."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from qiskit_qkd._validation import require_non_negative_int, require_positive_number
from qiskit_qkd.config import Scenario
from qiskit_qkd.sources import EmissionEvent
from qiskit_qkd.timing import assign_timing


class SourceLike(Protocol):
    def emit(self, *, rng: random.Random, time_s: float) -> EmissionEvent:
        """Sample an emission for one clock slot."""


class ChannelLike(Protocol):
    def transmit(self, rng: random.Random) -> bool:
        """Sample whether an emitted photon survives the channel."""


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
) -> PhysicalRound:
    """Sample source emission, channel transmission, and Bob timing metadata."""

    index = require_non_negative_int("index", index)
    slot_period_s = 1.0 / require_positive_number(
        "clock_rate_hz",
        scenario.clock_rate_hz,
    )
    emission_time_s = index * slot_period_s
    emission = source.emit(rng=rng, time_s=emission_time_s)
    transmitted = channel.transmit(rng) if emission.emitted else False
    timing = assign_timing(
        time_slot=index,
        pulses=scenario.pulses,
        clock_rate_hz=scenario.clock_rate_hz,
        gate_width_s=scenario.detector.gate_width_s,
        timing=scenario.timing,
        transmitted=transmitted,
        rng=rng,
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
        intensity_class=emission.intensity_class,
        transmitted=transmitted,
    )
