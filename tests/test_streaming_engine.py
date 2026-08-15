from __future__ import annotations

from dataclasses import replace

import pytest

from qiskit_qkd import (
    ChannelConfig,
    DetectorConfig,
    E91Config,
    PostProcessingConfig,
    ProtocolConfig,
    QiskitSamplerBackend,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from qiskit_qkd.postprocessing.sifting import bb84_sift_outcome
from qiskit_qkd.protocols import BB84Protocol, E91Protocol
from qiskit_qkd.protocols import bb84 as bb84_module
from qiskit_qkd.protocols.e91 import _sample_event_records
from qiskit_qkd.results import Event
from qiskit_qkd.timing import assign_timing, timing_context_from_scenario


def _e91_scenario(
    *,
    pulses: int = 256,
    seed: int = 20260812,
    event_sample_size: int = 0,
    store_full_event_log: bool = False,
) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(kind="entangled_pair"),
        channel=ChannelConfig(kind="ideal"),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        event_sample_size=event_sample_size,
        store_full_event_log=store_full_event_log,
    )


def test_e91_streaming_preserves_science_and_reservoir() -> None:
    aggregated_scenario = _e91_scenario(event_sample_size=16)
    full_scenario = replace(aggregated_scenario, store_full_event_log=True)
    aggregated = E91Protocol().run(
        aggregated_scenario,
        backend=QiskitSamplerBackend(seed=aggregated_scenario.seed),
    )
    full = E91Protocol().run(
        full_scenario,
        backend=QiskitSamplerBackend(seed=full_scenario.seed),
    )

    assert aggregated.metrics == full.metrics
    assert aggregated.classical == full.classical
    assert aggregated.bell == full.bell
    assert aggregated.qiskit == full.qiskit
    assert aggregated.event_sample == _sample_event_records(
        full.event_sample,
        sample_size=aggregated_scenario.event_sample_size,
        seed=aggregated_scenario.seed,
    )
    assert aggregated.aggregated is True


def test_e91_streaming_checks_cancellation_at_each_block() -> None:
    scenario = _e91_scenario(pulses=32)
    backend = QiskitSamplerBackend(seed=scenario.seed, max_circuits_per_job=8)
    checks = 0

    class Cancelled(RuntimeError):
        pass

    def check() -> None:
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise Cancelled

    with pytest.raises(Cancelled):
        E91Protocol().run(scenario, backend=backend, cancellation_check=check)
    assert checks >= 3


def test_e91_full_log_retains_every_event_explicitly() -> None:
    scenario = _e91_scenario(pulses=33, store_full_event_log=True)
    result = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(seed=scenario.seed),
    )
    assert result.aggregated is False
    assert len(result.event_sample) == scenario.pulses
    assert [event.index for event in result.event_sample] == list(
        range(scenario.pulses)
    )


def test_e91_reservoir_is_deterministic_and_bounded() -> None:
    scenario = _e91_scenario(pulses=257, event_sample_size=7)
    first = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(seed=scenario.seed, max_circuits_per_job=16),
    )
    second = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(seed=scenario.seed, max_circuits_per_job=16),
    )
    assert first.event_sample == second.event_sample
    assert len(first.event_sample) == scenario.event_sample_size
    assert [event.index for event in first.event_sample] != list(range(7))
    assert [event.index for event in first.event_sample] == sorted(
        event.index for event in first.event_sample
    )


def test_e91_streaming_keeps_rng_order_with_loss_and_detector_noise() -> None:
    base = _e91_scenario(pulses=257, seed=404, event_sample_size=11)
    cases = (
        replace(
            base,
            source=SourceConfig(
                kind="entangled_pair",
                preparation_error_probability=0.3,
            ),
        ),
        replace(
            base,
            channel=ChannelConfig(kind="fiber", distance_km=25.0),
            detector=DetectorConfig(
                kind="threshold",
                efficiency=0.8,
                dark_count_rate_hz=100.0,
                gate_width_s=1e-9,
            ),
        ),
        replace(
            base,
            timing=TimingConfig(
                jitter_std_s=2e-7,
                propagation_delay_s=1e-6,
                slot_assignment_policy="nearest",
            ),
        ),
        replace(
            base,
            detector=DetectorConfig(
                kind="threshold",
                efficiency=0.9,
                dark_count_rate_hz=500.0,
                gate_width_s=1e-9,
                dead_time_s=2e-6,
                afterpulse_probability=0.2,
            ),
        ),
    )
    for scenario in cases:
        aggregated = E91Protocol().run(
            scenario,
            backend=QiskitSamplerBackend(seed=scenario.seed, max_circuits_per_job=32),
        )
        full = E91Protocol().run(
            replace(scenario, store_full_event_log=True),
            backend=QiskitSamplerBackend(
                seed=scenario.seed,
                max_circuits_per_job=32,
            ),
        )
        assert aggregated.metrics == full.metrics
        assert aggregated.classical == full.classical
        assert aggregated.bell == full.bell
        assert aggregated.qiskit == full.qiskit
        assert aggregated.event_sample == _sample_event_records(
            full.event_sample,
            sample_size=scenario.event_sample_size,
            seed=scenario.seed,
        )


def test_bb84_builds_one_validated_event_per_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_event = bb84_module.Event
    post_init_calls = 0

    class CountingEvent(original_event):
        def __post_init__(self) -> None:
            nonlocal post_init_calls
            post_init_calls += 1
            super().__post_init__()

    monkeypatch.setattr(bb84_module, "Event", CountingEvent)
    scenario = Scenario(
        pulses=24,
        clock_rate_hz=1_000_000.0,
        seed=77,
        store_full_event_log=True,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )
    result = BB84Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(seed=scenario.seed),
    )
    assert post_init_calls == scenario.pulses
    assert len(result.event_sample) == scenario.pulses


def test_bb84_sifting_outcome_matches_event_wrapper_contract() -> None:
    event = Event(
        index=0,
        time_s=0.0,
        time_slot=0,
        assigned_slot=0,
        timing_status="in_gate",
        alice_bit=1,
        alice_basis="Z",
        bob_basis="Z",
        emitted=True,
        photon_number=1,
        surviving_photon_number=1,
        transmitted=True,
        detected=True,
        detection_origin="signal",
        bob_bit=0,
    )
    assert bb84_sift_outcome(
        detected=event.detected,
        assigned_slot=event.assigned_slot,
        time_slot=event.time_slot,
        alice_basis=event.alice_basis,
        bob_basis=event.bob_basis,
        alice_bit=event.alice_bit,
        bob_bit=event.bob_bit,
    ) == (True, True)


def test_timing_context_reuses_invariants_without_changing_assignment() -> None:
    scenario = Scenario(pulses=8, clock_rate_hz=2_000_000.0, seed=9)
    context = timing_context_from_scenario(scenario)
    import random

    legacy_rng = random.Random(9)
    context_rng = random.Random(9)
    legacy = assign_timing(
        time_slot=3,
        pulses=scenario.pulses,
        clock_rate_hz=scenario.clock_rate_hz,
        gate_width_s=scenario.detector.gate_width_s,
        timing=context.timing,
        transmitted=True,
        rng=legacy_rng,
    )
    optimized = assign_timing(
        time_slot=3,
        pulses=scenario.pulses,
        clock_rate_hz=scenario.clock_rate_hz,
        gate_width_s=scenario.detector.gate_width_s,
        timing=context.timing,
        transmitted=True,
        rng=context_rng,
        context=context,
    )
    assert optimized == legacy
