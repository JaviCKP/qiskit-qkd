from __future__ import annotations

import pytest

from qiskit_qkd.channels import ChannelCharacterizer, channel_state_from_scenario
from qiskit_qkd.config import (
    ChannelConfig,
    DynamicConfig,
    ParameterSchedule,
    Scenario,
)
from qiskit_qkd.temporal import ConstantProfile, ExponentialRampProfile


def test_channel_state_reports_physical_link_quantities() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=10.0,
        seed=7,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=10.0,
            attenuation_db_km=0.2,
            fixed_loss_db=1.0,
            background_count_rate_hz=250.0,
        ),
    )

    state = channel_state_from_scenario(scenario, time_s=2.5)

    assert state.time_s == 2.5
    assert state.distance_km == 10.0
    assert state.loss_db == pytest.approx(3.0)
    assert state.transmittance == pytest.approx(10 ** (-3.0 / 10.0))
    assert state.background_count_rate_hz == 250.0
    assert state.to_dict()["transmittance"] == pytest.approx(state.transmittance)


def test_characterize_time_resolves_schedules_into_flat_rows() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=10.0,
        seed=7,
        channel=ChannelConfig(kind="fiber", distance_km=5.0, attenuation_db_km=0.2),
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.depolarizing_probability",
                    profile=ConstantProfile(start_s=0.0, end_s=3.0, value=0.02),
                ),
                ParameterSchedule(
                    target="channel.background_count_rate_hz",
                    profile=ExponentialRampProfile(
                        start_s=5.0,
                        end_s=8.0,
                        start_value=100.0,
                        end_value=900.0,
                    ),
                ),
            ),
        ),
    )

    rows = ChannelCharacterizer().characterize_time(
        scenario,
        time_points_s=[0.0, 4.0, 6.5],
    )

    assert [row["time_s"] for row in rows] == [0.0, 4.0, 6.5]
    assert rows[0]["channel.depolarizing_probability"] == 0.02
    assert rows[1]["channel.depolarizing_probability"] == 0.0
    assert rows[2]["channel.background_count_rate_hz"] > 100.0
    assert rows[2]["channel.background_count_rate_hz"] < 900.0
    assert rows[2]["loss_db"] == pytest.approx(1.0)


def test_characterize_distance_returns_monotonic_fiber_loss_rows() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=10.0,
        seed=7,
        channel=ChannelConfig(kind="fiber", attenuation_db_km=0.2),
    )

    rows = ChannelCharacterizer().characterize_distance(
        scenario,
        distances_km=[0.0, 10.0, 20.0],
    )

    assert [row["distance_km"] for row in rows] == [0.0, 10.0, 20.0]
    assert [row["loss_db"] for row in rows] == [0.0, 2.0, 4.0]
    assert rows[0]["transmittance"] > rows[1]["transmittance"]
    assert rows[1]["transmittance"] > rows[2]["transmittance"]


def test_characterize_distance_reports_swept_dynamic_distance() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=10.0,
        seed=7,
        channel=ChannelConfig(kind="fiber", distance_km=5.0, attenuation_db_km=0.2),
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.distance_km",
                    profile=ConstantProfile(start_s=0.0, end_s=1.0, value=12.0),
                ),
            ),
        ),
    )

    rows = ChannelCharacterizer().characterize_distance(
        scenario,
        distances_km=[1.0, 2.0],
        time_s=0.0,
    )

    assert [row["distance_km"] for row in rows] == [1.0, 2.0]
    assert [row["channel.distance_km"] for row in rows] == [1.0, 2.0]
    assert [row["loss_db"] for row in rows] == [0.2, 0.4]
