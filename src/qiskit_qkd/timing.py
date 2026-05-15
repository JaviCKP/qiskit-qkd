"""Timing-window assignment for event-layer QKD simulations."""

from __future__ import annotations

import random
from dataclasses import dataclass

from qiskit_qkd._validation import require_positive_int, require_positive_number
from qiskit_qkd.config import TimingConfig


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

    @property
    def gate_center_s(self) -> float:
        return (self.bob_gate_start_s + self.bob_gate_end_s) / 2

    @property
    def signal_in_window(self) -> bool:
        return self.signal_assigned_slot is not None


def assign_timing(
    *,
    time_slot: int,
    pulses: int,
    clock_rate_hz: float,
    gate_width_s: float,
    timing: TimingConfig,
    transmitted: bool,
    rng: random.Random,
) -> TimingOutcome:
    """Assign a transmitted signal to a Bob detection gate when valid.

    `time_slot` is Alice and Bob's shared clock-window identifier. A lost photon
    does not move later windows; it simply gives this slot no signal arrival.
    """

    require_positive_int("pulses", pulses)
    slot_period_s = 1.0 / require_positive_number("clock_rate_hz", clock_rate_hz)
    require_positive_number("gate_width_s", gate_width_s)
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
