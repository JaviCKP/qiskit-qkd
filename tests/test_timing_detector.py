from __future__ import annotations

from dataclasses import replace

from qiskit_qkd import (
    ChannelConfig,
    DetectorConfig,
    Event,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from qiskit_qkd.postprocessing import sift_bb84_event
from qiskit_qkd.protocols import BB84Protocol


class CountingBackend:
    def __init__(self) -> None:
        self.rounds: list[tuple[int, str, str]] = []
        self.max_circuits_per_job = 512

    def measure_bb84_batch(
        self,
        rounds: list[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        self.rounds.extend(rounds)
        return tuple(
            alice_bit if alice_basis == bob_basis else 0
            for alice_bit, alice_basis, bob_basis in rounds
        )

    def measure_bb84(self, bit: int, alice_basis: str, bob_basis: str) -> int:
        self.rounds.append((bit, alice_basis, bob_basis))
        return bit if alice_basis == bob_basis else 0

    def provenance(self) -> dict[str, object]:
        return {"backend": "CountingBackend"}

    def qiskit_summary(self) -> dict[str, object]:
        return {"circuit_count": len(self.rounds)}


class ScriptedChannel:
    loss_db = 0.0

    def __init__(self, outcomes: list[bool]) -> None:
        self.outcomes = list(outcomes)

    def transmit(self, _rng) -> bool:
        if not self.outcomes:
            raise AssertionError("ScriptedChannel exhausted")
        return self.outcomes.pop(0)


def scenario(
    *,
    pulses: int = 8,
    seed: int = 101,
    clock_rate_hz: float = 1_000_000.0,
    detector: DetectorConfig | None = None,
    source: SourceConfig | None = None,
    timing: TimingConfig | None = None,
) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=clock_rate_hz,
        seed=seed,
        source=source or SourceConfig(emission_probability=1.0),
        channel=ChannelConfig(kind="ideal"),
        detector=detector
        or DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-6,
        ),
        timing=timing or TimingConfig(),
        store_full_event_log=True,
    )


def test_ideal_timing_keeps_phase3_detection_statistics() -> None:
    baseline = scenario(pulses=512, seed=103, timing=TimingConfig())
    explicit_ideal = replace(
        baseline,
        timing=TimingConfig(
            propagation_delay_s=0.0,
            jitter_std_s=0.0,
            clock_offset_s=0.0,
            clock_drift_ppm=0.0,
            slot_assignment_policy="discard",
        ),
    )

    first = BB84Protocol().run(baseline, backend=CountingBackend())
    second = BB84Protocol().run(explicit_ideal, backend=CountingBackend())

    assert first.metrics.to_dict() == second.metrics.to_dict()
    assert first.metrics.detected == baseline.pulses
    assert first.metrics.timing_discards == 0


def test_lost_slot_does_not_shift_later_signal_to_lost_slot(monkeypatch) -> None:
    scripted = ScriptedChannel([True, False, True])
    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.channel_from_config",
        lambda _config: scripted,
    )
    result = BB84Protocol().run(
        scenario(pulses=3, seed=107),
        backend=CountingBackend(),
    )

    events = result.event_sample
    assert [event.time_slot for event in events] == [0, 1, 2]
    assert events[1].transmitted is False
    assert events[1].detected is False
    assert events[1].assigned_slot is None
    assert events[2].transmitted is True
    assert events[2].detected is True
    assert events[2].assigned_slot == 2


def test_dark_count_is_assigned_to_its_bob_window_not_next_signal(monkeypatch) -> None:
    scripted = ScriptedChannel([False, True])
    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.channel_from_config",
        lambda _config: scripted,
    )
    detector = DetectorConfig(
        kind="threshold",
        efficiency=1.0,
        dark_count_rate_hz=1_000_000_000.0,
        gate_width_s=1.0,
        double_click_policy="random",
    )

    result = BB84Protocol().run(
        scenario(pulses=2, seed=109, clock_rate_hz=1.0, detector=detector),
        backend=CountingBackend(),
    )

    first, second = result.event_sample
    assert first.transmitted is False
    assert first.detected is True
    assert first.detection_origin == "dark"
    assert first.assigned_slot == 0
    assert second.transmitted is True
    assert second.assigned_slot == 1


def test_small_jitter_compared_with_gate_width_keeps_detection_rate() -> None:
    ideal = BB84Protocol().run(
        scenario(pulses=512, seed=113),
        backend=CountingBackend(),
    )
    jittered = BB84Protocol().run(
        scenario(
            pulses=512,
            seed=113,
            timing=TimingConfig(jitter_std_s=1e-9),
        ),
        backend=CountingBackend(),
    )

    assert ideal.metrics.detected == jittered.metrics.detected == 512
    assert jittered.metrics.timing_discards == 0


def test_large_clock_offset_discards_signal_arrivals_outside_bob_gate() -> None:
    result = BB84Protocol().run(
        scenario(
            pulses=32,
            seed=127,
            timing=TimingConfig(clock_offset_s=2e-6),
        ),
        backend=CountingBackend(),
    )

    assert result.metrics.detected == 0
    assert result.metrics.timing_discards == result.metrics.transmitted == 32
    assert {event.timing_status for event in result.event_sample} == {"early"}


def test_dead_time_reduces_detections_for_close_clicks() -> None:
    detector = DetectorConfig(
        kind="threshold",
        efficiency=1.0,
        dark_count_rate_hz=0.0,
        gate_width_s=0.01,
        dead_time_s=0.15,
    )

    result = BB84Protocol().run(
        scenario(
            pulses=5,
            seed=131,
            clock_rate_hz=10.0,
            detector=detector,
        ),
        backend=CountingBackend(),
    )

    assert result.metrics.detected == 3
    assert result.metrics.dead_time_discards == 2
    assert [event.timing_status for event in result.event_sample] == [
        "in_gate",
        "dead_time",
        "in_gate",
        "dead_time",
        "in_gate",
    ]


def test_afterpulse_probability_adds_false_clicks_after_real_detection(
    monkeypatch,
) -> None:
    baseline_channel = ScriptedChannel([True, False, False, False])
    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.channel_from_config",
        lambda _config: baseline_channel,
    )
    baseline = BB84Protocol().run(
        scenario(pulses=4, seed=137),
        backend=CountingBackend(),
    )

    afterpulse_channel = ScriptedChannel([True, False, False, False])
    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.channel_from_config",
        lambda _config: afterpulse_channel,
    )
    detector = DetectorConfig(
        kind="threshold",
        efficiency=1.0,
        dark_count_rate_hz=0.0,
        gate_width_s=1e-6,
        afterpulse_probability=1.0,
    )
    afterpulse = BB84Protocol().run(
        scenario(pulses=4, seed=137, detector=detector),
        backend=CountingBackend(),
    )

    assert baseline.metrics.detected == 1
    assert afterpulse.metrics.detected > baseline.metrics.detected
    assert afterpulse.metrics.afterpulse_clicks > 0
    assert any(
        event.detection_origin == "afterpulse" for event in afterpulse.event_sample
    )


def test_same_seed_reproduces_assigned_slots_times_and_metrics() -> None:
    reproducible = scenario(
        pulses=16,
        seed=139,
        timing=TimingConfig(
            propagation_delay_s=2e-6,
            jitter_std_s=1e-9,
            clock_offset_s=0.0,
            clock_drift_ppm=0.25,
        ),
    )

    first = BB84Protocol().run(reproducible, backend=CountingBackend())
    second = BB84Protocol().run(reproducible, backend=CountingBackend())

    first_timing = [
        (
            event.time_slot,
            event.arrival_time_s,
            event.bob_gate_start_s,
            event.bob_gate_end_s,
            event.assigned_slot,
            event.timing_status,
        )
        for event in first.event_sample
    ]
    second_timing = [
        (
            event.time_slot,
            event.arrival_time_s,
            event.bob_gate_start_s,
            event.bob_gate_end_s,
            event.assigned_slot,
            event.timing_status,
        )
        for event in second.event_sample
    ]

    assert first.metrics.to_dict() == second.metrics.to_dict()
    assert first_timing == second_timing


def test_sifting_uses_public_assigned_slot_not_hidden_signal_truth() -> None:
    shifted_signal = Event(
        index=0,
        time_s=0.0,
        time_slot=0,
        assigned_slot=1,
        timing_status="assigned_nearest",
        alice_bit=1,
        alice_basis="Z",
        bob_basis="Z",
        transmitted=True,
        detected=True,
        detection_origin="signal",
        bob_bit=1,
    )

    sifted = sift_bb84_event(shifted_signal)

    assert sifted.sifted is False
    assert sifted.error is None
