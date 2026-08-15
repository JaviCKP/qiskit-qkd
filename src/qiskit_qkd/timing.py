"""Timing-window assignment for event-layer QKD simulations."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    require_non_negative_number,
    require_positive_int,
    require_positive_number,
)
from qiskit_qkd.channels.impairments import effective_jitter_std_s
from qiskit_qkd.config import Scenario, TimingConfig
from qiskit_qkd.temporal import ParameterResolver


@dataclass(frozen=True, slots=True)
class TimingOutcome:
    """Timing metadata for one attempted Alice slot and one Bob gate."""

    time_slot: int
    emission_time_s: float
    expected_arrival_time_s: float
    arrival_time_s: float | None
    bob_gate_start_s: float
    bob_gate_end_s: float
    signal_assigned_slot: int | None
    timing_status: str


@dataclass(frozen=True, slots=True)
class TimingContext:
    """Invariant timing values reused by every slot in one execution."""

    slot_period_s: float
    gate_width_s: float
    timing: TimingConfig


@dataclass(frozen=True, slots=True)
class TimingState:
    """Analytical timing-gate state for one effective scenario."""

    time_s: float
    propagation_delay_s: float
    jitter_std_s: float
    effective_jitter_std_s: float
    gate_width_s: float
    in_gate_probability: float
    first_walkoff_slot: int | None
    clock_offset_s: float
    clock_drift_ppm: float

    def to_dict(self) -> JSONObject:
        return {
            "time_s": self.time_s,
            "propagation_delay_s": self.propagation_delay_s,
            "jitter_std_s": self.jitter_std_s,
            "effective_jitter_std_s": self.effective_jitter_std_s,
            "gate_width_s": self.gate_width_s,
            "in_gate_probability": self.in_gate_probability,
            "first_walkoff_slot": self.first_walkoff_slot,
            "clock_offset_s": self.clock_offset_s,
            "clock_drift_ppm": self.clock_drift_ppm,
        }


def timing_state_from_scenario(
    scenario: Scenario,
    *,
    time_s: float = 0.0,
    resolver: ParameterResolver | None = None,
) -> TimingState:
    """Return the analytical timing state at ``time_s``."""

    time = require_non_negative_number("time_s", time_s)
    active_resolver = resolver or ParameterResolver()
    effective = active_resolver.scenario_at(scenario, time_s=time)
    jitter = effective_jitter_std_s(effective)
    return TimingState(
        time_s=time,
        propagation_delay_s=effective.timing.propagation_delay_s,
        jitter_std_s=effective.timing.jitter_std_s,
        effective_jitter_std_s=jitter,
        gate_width_s=effective.detector.gate_width_s,
        in_gate_probability=_in_gate_probability(
            effective.detector.gate_width_s,
            jitter,
        ),
        first_walkoff_slot=_first_walkoff_slot(effective),
        clock_offset_s=effective.timing.clock_offset_s,
        clock_drift_ppm=effective.timing.clock_drift_ppm,
    )


def timing_context_from_scenario(scenario: Scenario) -> TimingContext:
    """Precompute timing values that are invariant across one scenario run."""

    slot_period_s = 1.0 / require_positive_number(
        "clock_rate_hz",
        scenario.clock_rate_hz,
    )
    gate_width_s = require_positive_number(
        "gate_width_s",
        scenario.detector.gate_width_s,
    )
    return TimingContext(
        slot_period_s=slot_period_s,
        gate_width_s=gate_width_s,
        timing=replace(
            scenario.timing,
            jitter_std_s=effective_jitter_std_s(scenario),
        ),
    )


def assign_timing(
    *,
    time_slot: int,
    pulses: int,
    clock_rate_hz: float,
    gate_width_s: float,
    timing: TimingConfig,
    transmitted: bool,
    rng: random.Random,
    context: TimingContext | None = None,
) -> TimingOutcome:
    """Assign a transmitted signal to a Bob detection gate when valid.

    `time_slot` is Alice and Bob's shared clock-window identifier. A lost photon
    does not move later windows; it simply gives this slot no signal arrival.
    """

    require_positive_int("pulses", pulses)
    if context is None:
        slot_period_s = 1.0 / require_positive_number(
            "clock_rate_hz",
            clock_rate_hz,
        )
        require_positive_number("gate_width_s", gate_width_s)
    else:
        slot_period_s = context.slot_period_s
        gate_width_s = context.gate_width_s
    emission_time_s = time_slot * slot_period_s
    expected_arrival_time_s = emission_time_s + timing.propagation_delay_s
    current_start_s, current_end_s = bob_gate_bounds_s(
        time_slot=time_slot,
        slot_period_s=slot_period_s,
        gate_width_s=gate_width_s,
        timing=timing,
    )

    if not transmitted:
        return TimingOutcome(
            time_slot=time_slot,
            emission_time_s=emission_time_s,
            expected_arrival_time_s=expected_arrival_time_s,
            arrival_time_s=None,
            bob_gate_start_s=current_start_s,
            bob_gate_end_s=current_end_s,
            signal_assigned_slot=None,
            timing_status="no_signal",
        )

    jitter_s = rng.gauss(0.0, timing.jitter_std_s) if timing.jitter_std_s else 0.0
    arrival_time_s = expected_arrival_time_s + jitter_s
    if current_start_s <= arrival_time_s <= current_end_s:
        return TimingOutcome(
            time_slot=time_slot,
            emission_time_s=emission_time_s,
            expected_arrival_time_s=expected_arrival_time_s,
            arrival_time_s=arrival_time_s,
            bob_gate_start_s=current_start_s,
            bob_gate_end_s=current_end_s,
            signal_assigned_slot=time_slot,
            timing_status="in_gate",
        )

    if timing.slot_assignment_policy == "nearest":
        assigned_slot = nearest_bob_slot(
            arrival_time_s=arrival_time_s,
            pulses=pulses,
            slot_period_s=slot_period_s,
            timing=timing,
        )
        if assigned_slot is not None:
            assigned_start_s, assigned_end_s = bob_gate_bounds_s(
                time_slot=assigned_slot,
                slot_period_s=slot_period_s,
                gate_width_s=gate_width_s,
                timing=timing,
            )
            if assigned_start_s <= arrival_time_s <= assigned_end_s:
                return TimingOutcome(
                    time_slot=time_slot,
                    emission_time_s=emission_time_s,
                    expected_arrival_time_s=expected_arrival_time_s,
                    arrival_time_s=arrival_time_s,
                    bob_gate_start_s=assigned_start_s,
                    bob_gate_end_s=assigned_end_s,
                    signal_assigned_slot=assigned_slot,
                    timing_status="assigned_nearest",
                )

    timing_status = "early" if arrival_time_s < current_start_s else "late"
    return TimingOutcome(
        time_slot=time_slot,
        emission_time_s=emission_time_s,
        expected_arrival_time_s=expected_arrival_time_s,
        arrival_time_s=arrival_time_s,
        bob_gate_start_s=current_start_s,
        bob_gate_end_s=current_end_s,
        signal_assigned_slot=None,
        timing_status=timing_status,
    )


def bob_gate_bounds_s(
    *,
    time_slot: int,
    slot_period_s: float,
    gate_width_s: float,
    timing: TimingConfig,
) -> tuple[float, float]:
    center_s = bob_gate_center_s(
        time_slot=time_slot,
        slot_period_s=slot_period_s,
        timing=timing,
    )
    half_width_s = gate_width_s / 2
    return center_s - half_width_s, center_s + half_width_s


def bob_gate_center_s(
    *,
    time_slot: int,
    slot_period_s: float,
    timing: TimingConfig,
) -> float:
    bob_period_s = slot_period_s * (1.0 + timing.clock_drift_ppm * 1e-6)
    return (
        timing.propagation_delay_s
        + timing.clock_offset_s
        + time_slot * bob_period_s
    )


def nearest_bob_slot(
    *,
    arrival_time_s: float,
    pulses: int,
    slot_period_s: float,
    timing: TimingConfig,
) -> int | None:
    bob_period_s = slot_period_s * (1.0 + timing.clock_drift_ppm * 1e-6)
    normalized = (
        arrival_time_s - timing.propagation_delay_s - timing.clock_offset_s
    ) / bob_period_s
    nearest = round(normalized)
    if 0 <= nearest < pulses:
        return nearest
    return None


def _in_gate_probability(gate_width_s: float, jitter_std_s: float) -> float:
    if jitter_std_s == 0.0:
        return 1.0
    return math.erf(gate_width_s / (2.0 * math.sqrt(2.0) * jitter_std_s))


def _first_walkoff_slot(scenario: Scenario) -> int | None:
    half_gate_s = scenario.detector.gate_width_s / 2.0
    offset_s = scenario.timing.clock_offset_s
    if abs(offset_s) > half_gate_s:
        return 0
    drift_per_slot_s = (
        (1.0 / scenario.clock_rate_hz) * scenario.timing.clock_drift_ppm * 1e-6
    )
    if drift_per_slot_s == 0.0:
        return None
    if drift_per_slot_s > 0.0:
        threshold = (half_gate_s - offset_s) / drift_per_slot_s
    else:
        threshold = (-half_gate_s - offset_s) / drift_per_slot_s
    slot = max(0, math.floor(threshold) + 1)
    return slot if slot < scenario.pulses else None
