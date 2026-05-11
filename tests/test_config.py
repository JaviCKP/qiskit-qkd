import pytest

from qiskit_qkd import (
    ChannelConfig,
    DetectorConfig,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
    make_rng,
)


def build_scenario(seed: int = 7) -> Scenario:
    return Scenario(
        pulses=1_000,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        protocol=ProtocolConfig(name="bb84", basis_choices=("Z", "X")),
        source=SourceConfig(
            kind="ideal_single_photon",
            emission_probability=0.95,
            preparation_error_probability=0.01,
        ),
        channel=ChannelConfig(
            kind="fiber",
            distance_km=25.0,
            attenuation_db_km=0.2,
            fixed_loss_db=1.0,
            depolarizing_probability=0.02,
            phase_damping_probability=0.03,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.2,
            dark_count_rate_hz=100.0,
            gate_width_s=1e-9,
            readout_error_probability=0.01,
            double_click_policy="random",
        ),
        post_processing=PostProcessingConfig(
            sifting_enabled=True,
            qber_abort_threshold=0.11,
            error_correction_efficiency=1.2,
            privacy_amplification_enabled=True,
        ),
        event_sample_size=3,
        metadata={"label": "phase-1"},
    )


def test_scenario_keeps_explicit_units_and_duration() -> None:
    scenario = build_scenario()

    assert scenario.pulses == 1_000
    assert scenario.clock_rate_hz == 1_000_000.0
    assert scenario.duration_s == 0.001
    assert scenario.channel.distance_km == 25.0
    assert scenario.detector.gate_width_s == 1e-9


def test_same_scenario_and_seed_produce_same_summary() -> None:
    first = build_scenario(seed=7)
    second = Scenario.from_json(first.to_json())
    different_seed = build_scenario(seed=8)

    assert first.digest() == second.digest()
    assert first.reproducibility_summary() == second.reproducibility_summary()
    assert first.reproducibility_summary() != different_seed.reproducibility_summary()


def test_make_rng_is_centralized_and_reproducible() -> None:
    first = make_rng(11)
    second = make_rng(11)

    assert [first.random() for _ in range(5)] == [second.random() for _ in range(5)]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Scenario(pulses=0, clock_rate_hz=1.0, seed=1),
        lambda: Scenario(pulses=1, clock_rate_hz=0.0, seed=1),
        lambda: Scenario(pulses=1, clock_rate_hz=1.0, seed=-1),
        lambda: SourceConfig(emission_probability=1.1),
        lambda: SourceConfig(mean_photon_number=0.0),
        lambda: ChannelConfig(distance_km=-0.1),
        lambda: ChannelConfig(attenuation_db_km=-0.1),
        lambda: DetectorConfig(efficiency=-0.1),
        lambda: DetectorConfig(gate_width_s=0.0),
        lambda: DetectorConfig(double_click_policy="keep"),
        lambda: PostProcessingConfig(error_correction_efficiency=0.9),
    ],
)
def test_invalid_parameters_raise(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()
