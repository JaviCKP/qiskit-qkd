import json

import pytest

from qiskit_qkd import (
    ChannelConfig,
    Event,
    Metrics,
    Scenario,
    SimulationResult,
    __version__,
)


def build_scenario(event_sample_size: int = 1) -> Scenario:
    return Scenario(
        pulses=100,
        clock_rate_hz=10_000.0,
        seed=123,
        channel=ChannelConfig(kind="fiber", distance_km=5.0, attenuation_db_km=0.2),
        event_sample_size=event_sample_size,
    )


def build_metrics() -> Metrics:
    return Metrics(
        pulses=100,
        emitted=95,
        transmitted=80,
        detected=75,
        sifted=38,
        errors=2,
        qber=2 / 38,
        loss_db=1.0,
        gain=0.75,
        raw_detection_rate_hz=7_500.0,
        sifted_key_rate_bps=3_800.0,
        secret_key_rate_bps=1_000.0,
        abort=False,
        eve_intercepted_fraction=0.0,
        eve_information_estimate=0.0,
        chsh_s=2.5,
    )


def test_scenario_json_roundtrip_is_stable() -> None:
    scenario = build_scenario()

    payload = scenario.to_json()
    restored = Scenario.from_json(payload)

    assert restored == scenario
    assert json.loads(restored.to_json()) == json.loads(payload)
    assert json.loads(payload)["channel"]["distance_km"] == 5.0


def test_simulation_result_json_contains_required_sections() -> None:
    scenario = build_scenario(event_sample_size=1)
    event = Event(
        index=0,
        time_s=0.0,
        alice_bit=1,
        alice_basis="X",
        bob_basis="X",
        emitted=True,
        photon_number=1,
        transmitted=True,
        detected=True,
        detection_origin="signal",
        bob_bit=1,
        sifted=True,
        error=False,
        eve_basis="X",
        tags={"source": "unit-test"},
    )
    result = SimulationResult(
        scenario=scenario,
        metrics=build_metrics(),
        provenance={"backend": "aggregate-test"},
        event_sample=(event,),
    )

    payload = result.to_dict()

    assert payload["scenario"] == scenario.to_dict()
    assert payload["metrics"] == build_metrics().to_dict()
    assert payload["library_version"] == __version__
    assert payload["provenance"]["library_version"] == __version__
    assert payload["provenance"]["seed"] == scenario.seed
    assert payload["provenance"]["scenario_digest"] == scenario.digest()
    assert payload["provenance"]["backend"] == "aggregate-test"
    assert payload["event_sample"] == [event.to_dict()]
    assert payload["event_sample"][0]["eve_basis"] == "X"


def test_simulation_result_json_roundtrip_is_stable() -> None:
    result = SimulationResult(
        scenario=build_scenario(event_sample_size=0),
        metrics=build_metrics(),
    )

    restored = SimulationResult.from_json(result.to_json())

    assert restored.to_dict() == result.to_dict()
    assert restored.summary() == result.summary()
    assert restored.to_dict()["event_sample"] == []


def test_event_serialization_order_follows_round_lifecycle() -> None:
    event = Event(index=0, time_s=0.0)

    assert list(event.to_dict()) == [
        "index",
        "time_slot",
        "time_s",
        "emission_time_s",
        "expected_arrival_time_s",
        "arrival_time_s",
        "bob_gate_start_s",
        "bob_gate_end_s",
        "assigned_slot",
        "timing_status",
        "alice_bit",
        "alice_basis",
        "bob_basis",
        "emitted",
        "photon_number",
        "intensity_class",
        "transmitted",
        "detected",
        "detection_origin",
        "bob_bit",
        "detection_pattern",
        "sifted",
        "error",
        "party",
        "phase_slice",
        "bsm_success",
        "eve_action",
        "eve_basis",
        "eve_detectable",
        "tags",
    ]


def test_event_sample_is_not_stored_by_default() -> None:
    scenario = build_scenario(event_sample_size=0)
    event = Event(index=0, time_s=0.0)

    with pytest.raises(ValueError):
        SimulationResult(
            scenario=scenario,
            metrics=build_metrics(),
            event_sample=(event,),
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Event(index=-1, time_s=0.0),
        lambda: Event(index=0, time_s=-0.1),
        lambda: Event(index=0, time_s=0.0, alice_bit=2),
        lambda: Event(index=0, time_s=0.0, detection_origin="lost"),
        lambda: Metrics(pulses=10, emitted=11),
        lambda: Metrics(pulses=10, emitted=5, transmitted=6),
        lambda: Metrics(pulses=10, sifted=1, errors=2),
        lambda: Metrics(pulses=10, qber=1.1),
        lambda: Metrics(pulses=10, chsh_s=4.1),
    ],
)
def test_result_validation_rejects_invalid_values(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()
