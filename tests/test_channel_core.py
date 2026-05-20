from __future__ import annotations

from qiskit_qkd.channel_core import prepare_physical_round
from qiskit_qkd.config import ChannelConfig, DetectorConfig, Scenario, SourceConfig
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.sources import EmissionEvent


class FailingChannel:
    loss_db = 0.0

    def transmit(self, _rng) -> bool:
        raise AssertionError("channel should not be sampled when no photon is emitted")


class ScriptedChannel:
    loss_db = 0.0

    def __init__(self, outcomes: list[bool]) -> None:
        self.outcomes = list(outcomes)

    def transmit(self, _rng) -> bool:
        return self.outcomes.pop(0)


class ScriptedSource:
    def __init__(self, emissions: list[EmissionEvent]) -> None:
        self.emissions = list(emissions)

    def emit(self, *, rng, time_s: float) -> EmissionEvent:
        event = self.emissions.pop(0)
        assert event.time_s == time_s
        return event


def scenario() -> Scenario:
    return Scenario(
        pulses=4,
        clock_rate_hz=1_000_000.0,
        seed=7,
        source=SourceConfig(emission_probability=1.0),
        channel=ChannelConfig(kind="ideal"),
        detector=DetectorConfig(gate_width_s=1e-6),
    )


def test_physical_round_skips_channel_when_source_does_not_emit() -> None:
    source = ScriptedSource(
        [EmissionEvent(emitted=False, photon_number=0, time_s=0.0)],
    )

    physical = prepare_physical_round(
        index=0,
        scenario=scenario(),
        source=source,
        channel=FailingChannel(),
        rng=make_rng(11),
    )

    assert physical.emitted is False
    assert physical.photon_number == 0
    assert physical.transmitted is False
    assert physical.signal_assigned_slot is None
    assert physical.timing_status == "no_signal"


def test_lost_physical_round_keeps_its_original_time_slot() -> None:
    physical = prepare_physical_round(
        index=2,
        scenario=scenario(),
        source=ScriptedSource(
            [EmissionEvent(emitted=True, photon_number=1, time_s=2e-6)],
        ),
        channel=ScriptedChannel([False]),
        rng=make_rng(13),
    )

    assert physical.index == 2
    assert physical.time_slot == 2
    assert physical.transmitted is False
    assert physical.signal_assigned_slot is None
    assert physical.assigned_signal_present is False


def test_transmitted_physical_round_is_assigned_to_bob_gate() -> None:
    physical = prepare_physical_round(
        index=3,
        scenario=scenario(),
        source=ScriptedSource(
            [EmissionEvent(emitted=True, photon_number=1, time_s=3e-6)],
        ),
        channel=ScriptedChannel([True]),
        rng=make_rng(17),
    )

    assert physical.emitted is True
    assert physical.transmitted is True
    assert physical.signal_assigned_slot == 3
    assert physical.assigned_signal_present is True
    assert (
        physical.bob_gate_start_s
        <= physical.arrival_time_s
        <= physical.bob_gate_end_s
    )
