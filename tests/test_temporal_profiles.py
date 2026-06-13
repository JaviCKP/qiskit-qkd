from __future__ import annotations

import pytest

from qiskit_qkd.config import DynamicConfig, ParameterSchedule, Scenario
from qiskit_qkd.temporal import (
    ConstantProfile,
    ExponentialRampProfile,
    LinearRampProfile,
    ParameterResolver,
    profile_from_dict,
)


def test_constant_profile_applies_only_inside_its_time_window() -> None:
    profile = ConstantProfile(start_s=0.0, end_s=3.0, value=0.02)

    assert profile.value_at(-0.1) is None
    assert profile.value_at(0.0) == 0.02
    assert profile.value_at(2.5) == 0.02
    assert profile.value_at(3.0) == 0.02
    assert profile.value_at(3.1) is None
    assert profile_from_dict(profile.to_dict()) == profile


def test_exponential_ramp_profile_reaches_endpoints_and_is_not_linear() -> None:
    profile = ExponentialRampProfile(
        start_s=5.0,
        end_s=8.0,
        start_value=0.01,
        end_value=0.09,
        curve=3.0,
    )

    assert profile.value_at(4.9) is None
    assert profile.value_at(5.0) == pytest.approx(0.01)
    assert profile.value_at(8.0) == pytest.approx(0.09)
    assert profile.value_at(6.5) < 0.05
    assert profile_from_dict(profile.to_dict()) == profile


def test_linear_ramp_profile_interpolates_between_endpoints() -> None:
    profile = LinearRampProfile(
        start_s=1.0,
        end_s=3.0,
        start_value=10.0,
        end_value=30.0,
    )

    assert profile.value_at(0.5) is None
    assert profile.value_at(1.0) == pytest.approx(10.0)
    assert profile.value_at(2.0) == pytest.approx(20.0)
    assert profile.value_at(3.0) == pytest.approx(30.0)


def test_profiles_reject_invalid_windows_and_unknown_kinds() -> None:
    with pytest.raises(ValueError):
        ConstantProfile(start_s=3.0, end_s=3.0, value=0.1)
    with pytest.raises(ValueError):
        ExponentialRampProfile(
            start_s=0.0,
            end_s=1.0,
            start_value=0.0,
            end_value=1.0,
            curve=0.0,
        )
    with pytest.raises(ValueError):
        profile_from_dict({"kind": "quadratic", "start_s": 0.0, "end_s": 1.0})


def test_parameter_resolver_applies_active_schedules_without_mutating_base() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=10.0,
        seed=7,
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.depolarizing_probability",
                    profile=ConstantProfile(start_s=0.0, end_s=3.0, value=0.02),
                ),
                ParameterSchedule(
                    target="eavesdropper.intercept_probability",
                    profile=ExponentialRampProfile(
                        start_s=5.0,
                        end_s=8.0,
                        start_value=0.1,
                        end_value=0.9,
                    ),
                ),
            ),
        ),
    )

    resolver = ParameterResolver()
    during_step = resolver.scenario_at(scenario, time_s=2.0)
    during_ramp = resolver.scenario_at(scenario, time_s=6.5)
    outside = resolver.scenario_at(scenario, time_s=4.0)

    assert during_step.channel.depolarizing_probability == 0.02
    assert during_ramp.eavesdropper.intercept_probability > 0.1
    assert during_ramp.eavesdropper.intercept_probability < 0.9
    assert outside.channel.depolarizing_probability == 0.0
    assert outside.eavesdropper.intercept_probability == 0.0
    assert scenario.channel.depolarizing_probability == 0.0
    assert scenario.eavesdropper.intercept_probability == 0.0


def test_scenario_at_consumes_dynamic_schedules() -> None:
    scenario = Scenario(
        pulses=10,
        clock_rate_hz=1.0,
        seed=5,
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="detector.efficiency",
                    profile=ConstantProfile(start_s=0.0, end_s=1.0, value=0.5),
                ),
            ),
        ),
    )

    effective = ParameterResolver().scenario_at(scenario, time_s=0.5)
    outside = ParameterResolver().scenario_at(scenario, time_s=2.0)

    assert effective.detector.efficiency == 0.5
    assert effective.dynamic.parameter_schedules == ()
    assert outside.detector.efficiency == 1.0
    assert outside.dynamic.parameter_schedules == ()
    assert scenario.dynamic.parameter_schedules != ()


def test_dynamic_schedules_are_serializable_on_scenario() -> None:
    scenario = Scenario(
        pulses=10,
        clock_rate_hz=1.0,
        seed=5,
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="detector.efficiency",
                    profile=ConstantProfile(start_s=0.0, end_s=1.0, value=0.5),
                ),
            ),
        ),
    )

    round_trip = Scenario.from_json(scenario.to_json())

    assert round_trip.dynamic == scenario.dynamic
    assert round_trip.dynamic.parameter_schedules[0].target == "detector.efficiency"


def test_parameter_schedule_validates_targets_and_effective_values() -> None:
    with pytest.raises(ValueError):
        ParameterSchedule(
            target="channel.not_a_field",
            profile=ConstantProfile(start_s=0.0, end_s=1.0, value=0.1),
        )

    scenario = Scenario(
        pulses=10,
        clock_rate_hz=1.0,
        seed=5,
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.depolarizing_probability",
                    profile=ConstantProfile(start_s=0.0, end_s=1.0, value=1.5),
                ),
            ),
        ),
    )

    with pytest.raises(ValueError):
        ParameterResolver().scenario_at(scenario, time_s=0.5)
