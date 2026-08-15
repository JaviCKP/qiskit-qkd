from pathlib import Path

import pytest

from qiskit_qkd import (
    ChannelConfig,
    DetectorConfig,
    E91Config,
    EveConfig,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
    make_rng,
)
from qiskit_qkd.config import (
    UnsupportedScenarioVersionError,
    migrate_scenario_v1_to_v2,
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
            polarization_rotation_y_rad=0.04,
            polarization_rotation_z_rad=-0.02,
            background_count_rate_hz=250.0,
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
    assert scenario.channel.polarization_rotation_y_rad == 0.04
    assert scenario.channel.polarization_rotation_z_rad == -0.02
    assert scenario.channel.background_count_rate_hz == 250.0
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


def test_vacuum_decoy_source_can_use_zero_mean_photon_number() -> None:
    source = SourceConfig(kind="weak_coherent", mean_photon_number=0.0)

    assert source.mean_photon_number == 0.0
    assert source.to_dict()["mean_photon_number"] == 0.0


def test_eve_config_normalizes_kind_aliases_to_canonical_names() -> None:
    assert EveConfig(kind="no_eve").kind == "none"
    assert EveConfig(kind="pns").kind == "photon_number_splitting"
    assert EveConfig(kind="no_eve").to_dict() == EveConfig(kind="none").to_dict()


def test_channel_config_defaults_to_telecom_fiber_attenuation() -> None:
    assert ChannelConfig().attenuation_db_km == 0.2
    assert ChannelConfig.from_dict({}).attenuation_db_km == 0.2


def test_e91_config_accepts_equivalent_chsh_sign_and_term_order() -> None:
    terms = (
        (1, 1, 1),
        (0, 1, -1),
        (1, 0, -1),
        (0, 0, -1),
    )

    config = E91Config(chsh_terms=terms)

    assert config.chsh_terms == terms
    assert config.classical_bound == 2.0
    assert E91Config.from_dict(config.to_dict()) == config


@pytest.mark.parametrize(
    ("terms", "exception", "match"),
    [
        (None, TypeError, "tuple or list"),
        ((), ValueError, "exactly four"),
        (
            ((0, 0, 1), (1, 0, 1), (0, 1, 1)),
            ValueError,
            "exactly four",
        ),
        (
            (
                (0, 0, 1),
                (1, 0, 1),
                (0, 1, 1),
                (1, 1, -1),
                (2, 2, -1),
            ),
            ValueError,
            "exactly four",
        ),
        (
            ((0, 0), (1, 0, 1), (0, 1, 1), (1, 1, -1)),
            TypeError,
            "exactly three values",
        ),
        (
            ((0, 0, 1), (0, 0, 1), (1, 0, 1), (1, 1, -1)),
            ValueError,
            "unique setting pairs",
        ),
        (
            ((0, 0, 1), (1, 0, 1), (2, 0, 1), (2, 1, -1)),
            ValueError,
            "Cartesian product",
        ),
        (
            ((0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)),
            ValueError,
            "product -1",
        ),
        (
            ((0, 0, True), (1, 0, 1), (0, 1, 1), (1, 1, -1)),
            TypeError,
            "integer -1 or 1",
        ),
        (
            ((0, 0, 1.0), (1, 0, 1), (0, 1, 1), (1, 1, -1)),
            TypeError,
            "integer -1 or 1",
        ),
        (
            ((0, 0, "1"), (1, 0, 1), (0, 1, 1), (1, 1, -1)),
            TypeError,
            "integer -1 or 1",
        ),
        (
            ((0, 0, 0), (1, 0, 1), (0, 1, 1), (1, 1, -1)),
            ValueError,
            "integer -1 or 1",
        ),
    ],
)
def test_e91_config_rejects_invalid_chsh_terms(
    terms,
    exception: type[Exception],
    match: str,
) -> None:
    with pytest.raises(exception, match=match):
        E91Config(chsh_terms=terms)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Scenario(pulses=0, clock_rate_hz=1.0, seed=1),
        lambda: Scenario(pulses=1, clock_rate_hz=0.0, seed=1),
        lambda: Scenario(pulses=1, clock_rate_hz=1.0, seed=-1),
        lambda: ProtocolConfig(name="six_state"),
        lambda: ProtocolConfig(name="bb84", basis_choices=("Z", "Y")),
        lambda: ProtocolConfig(name="bb84", basis_choices=("Z", "Z")),
        lambda: SourceConfig(kind="nonsense"),
        lambda: SourceConfig(kind="weak_coherent"),
        lambda: SourceConfig(emission_probability=1.1),
        lambda: SourceConfig(mean_photon_number=-0.1),
        lambda: ChannelConfig(kind="coax"),
        lambda: ChannelConfig(distance_km=-0.1),
        lambda: ChannelConfig(attenuation_db_km=-0.1),
        lambda: ChannelConfig(wavelength_nm=0.0),
        lambda: ChannelConfig(transmitter_aperture_m=0.0),
        lambda: ChannelConfig(receiver_aperture_m=0.0),
        lambda: ChannelConfig(beam_divergence_rad=-1e-6),
        lambda: ChannelConfig(atmospheric_extinction_db_km=-0.1),
        lambda: ChannelConfig(scintillation_sigma=-0.1),
        lambda: ChannelConfig(pointing_jitter_rad=-1e-6),
        lambda: ChannelConfig(underwater_extinction_m_inv=-0.01),
        lambda: ChannelConfig(underwater_scattering_broadening_ns_per_m=-0.01),
        lambda: ChannelConfig(background_count_rate_hz=-1.0),
        lambda: ChannelConfig(polarization_rotation_y_rad=float("inf")),
        lambda: DetectorConfig(efficiency=-0.1),
        lambda: DetectorConfig(kind="camera"),
        lambda: DetectorConfig(gate_width_s=0.0),
        lambda: DetectorConfig(double_click_policy="keep"),
        lambda: PostProcessingConfig(error_correction_efficiency=0.9),
        lambda: PostProcessingConfig(decoy_security_method="finite_key"),
    ],
)
def test_invalid_parameters_raise(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_scenario_v1_round_trip_preserves_wire_version_and_digest() -> None:
    current = build_scenario()
    legacy = current.to_dict(schema_version=1)
    restored = Scenario.from_dict(legacy)

    assert restored.to_dict()["schema_version"] == 1
    assert restored.digest() == current.digest()


def test_scenario_v1_to_v2_migration_is_explicit_and_digest_stable() -> None:
    current = build_scenario()
    legacy = current.to_dict(schema_version=1)

    migrated = migrate_scenario_v1_to_v2(legacy)

    assert migrated["schema_version"] == 2
    assert Scenario.from_dict(migrated).digest() == current.digest()
    assert legacy["schema_version"] == 1


def test_scenario_future_version_reports_found_version_and_solution() -> None:
    payload = build_scenario().to_dict(schema_version=2)
    payload["schema_version"] = 99

    with pytest.raises(UnsupportedScenarioVersionError) as caught:
        Scenario.from_dict(payload)

    assert caught.value.found_version == 99
    assert "upgrade" in caught.value.suggestion


def test_historical_v1_fixture_is_read_without_version_drift() -> None:
    fixture = Path(__file__).parent / "fixtures" / "contracts" / "scenario_v1.json"
    payload = fixture.read_text(encoding="utf-8")
    scenario = Scenario.from_json(payload)

    assert scenario.to_dict()["schema_version"] == 1
    assert scenario.pulses == 8
