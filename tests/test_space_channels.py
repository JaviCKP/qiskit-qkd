from __future__ import annotations

import math

import pytest

from qiskit_qkd.channels import (
    ChannelCharacterizer,
    FreeSpaceChannel,
    SpaceChannel,
    UnderwaterChannel,
    channel_from_config,
    effective_jitter_std_s,
    temporal_broadening_s,
)
from qiskit_qkd.config import ChannelConfig, Scenario
from qiskit_qkd.reproducibility import make_rng


def test_space_channel_geometric_loss_decreases_with_distance() -> None:
    near = SpaceChannel(
        distance_km=500.0,
        transmitter_aperture_m=0.20,
        receiver_aperture_m=0.50,
        wavelength_nm=850.0,
        fixed_loss_db=1.0,
    )
    far = SpaceChannel(
        distance_km=2_000.0,
        transmitter_aperture_m=0.20,
        receiver_aperture_m=0.50,
        wavelength_nm=850.0,
        fixed_loss_db=1.0,
    )

    assert 0.0 < far.transmittance() < near.transmittance() < 1.0
    assert far.loss_db > near.loss_db > 0.0


def test_free_space_channel_combines_geometric_and_atmospheric_loss() -> None:
    space = SpaceChannel(
        distance_km=20.0,
        transmitter_aperture_m=0.15,
        receiver_aperture_m=0.40,
        wavelength_nm=850.0,
    )
    free_space = FreeSpaceChannel(
        distance_km=20.0,
        transmitter_aperture_m=0.15,
        receiver_aperture_m=0.40,
        wavelength_nm=850.0,
        atmospheric_extinction_db_km=0.3,
    )

    assert free_space.transmittance() == pytest.approx(
        space.transmittance() * 10 ** (-(0.3 * 20.0) / 10.0),
    )
    assert free_space.loss_db == pytest.approx(space.loss_db + 6.0)


def test_underwater_channel_uses_beer_lambert_extinction_per_meter() -> None:
    channel = UnderwaterChannel(
        distance_km=0.10,
        transmitter_aperture_m=10.0,
        receiver_aperture_m=10.0,
        wavelength_nm=500.0,
        underwater_extinction_m_inv=0.05,
    )

    assert channel.transmittance() == pytest.approx(math.exp(-5.0), rel=1e-5)
    assert channel.loss_db == pytest.approx(-10.0 * math.log10(math.exp(-5.0)))


def test_stochastic_fading_samples_are_reproducible_and_bounded() -> None:
    channel = FreeSpaceChannel(
        distance_km=500.0,
        transmitter_aperture_m=0.20,
        receiver_aperture_m=0.50,
        wavelength_nm=850.0,
        scintillation_sigma=0.35,
        pointing_jitter_rad=1e-7,
    )

    first = channel.sample_transmittance(make_rng(123))
    second = channel.sample_transmittance(make_rng(123))

    assert first == second
    assert 0.0 <= first <= 1.0
    assert first != pytest.approx(channel.transmittance())


def test_channel_config_roundtrips_new_optical_channel_parameters() -> None:
    config = ChannelConfig(
        kind="free_space",
        distance_km=42.0,
        wavelength_nm=810.0,
        transmitter_aperture_m=0.12,
        receiver_aperture_m=0.80,
        beam_divergence_rad=2e-6,
        atmospheric_extinction_db_km=0.15,
        scintillation_sigma=0.2,
        pointing_jitter_rad=5e-7,
        underwater_extinction_m_inv=0.03,
        underwater_scattering_broadening_ns_per_m=0.01,
    )

    restored = ChannelConfig.from_dict(config.to_dict())

    assert restored == config
    assert restored.to_dict()["wavelength_nm"] == 810.0
    assert restored.to_dict()["underwater_extinction_m_inv"] == 0.03


def test_channel_factory_builds_non_fiber_media() -> None:
    assert isinstance(channel_from_config(ChannelConfig(kind="space")), SpaceChannel)
    assert isinstance(
        channel_from_config(ChannelConfig(kind="free_space")),
        FreeSpaceChannel,
    )
    assert isinstance(
        channel_from_config(ChannelConfig(kind="underwater")),
        UnderwaterChannel,
    )


def test_channel_characterizer_reports_non_fiber_link_budget_columns() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=1_000_000.0,
        seed=7,
        channel=ChannelConfig(
            kind="free_space",
            distance_km=20.0,
            transmitter_aperture_m=0.15,
            receiver_aperture_m=0.40,
            atmospheric_extinction_db_km=0.3,
            scintillation_sigma=0.2,
            pointing_jitter_rad=1e-7,
        ),
    )

    row = ChannelCharacterizer().characterize_time(
        scenario,
        time_points_s=[0.0],
    )[0]

    assert row["channel_kind"] == "free_space"
    assert row["geometric_transmittance"] > 0.0
    assert row["atmospheric_loss_db"] == pytest.approx(6.0)
    assert row["scintillation_sigma"] == 0.2
    assert row["pointing_jitter_rad"] == 1e-7


def test_underwater_scattering_broadening_contributes_to_effective_jitter() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=1_000_000.0,
        seed=7,
        channel=ChannelConfig(
            kind="underwater",
            distance_km=0.10,
            underwater_scattering_broadening_ns_per_m=0.02,
        ),
    )

    assert temporal_broadening_s(scenario.channel) == pytest.approx(2e-9)
    assert effective_jitter_std_s(scenario) == pytest.approx(2e-9)
