from __future__ import annotations

import json

import pytest

from qiskit_qkd.config import (
    ChannelConfig,
    DecoyIntensity,
    DynamicConfig,
    EveConfig,
    ParameterSchedule,
    ProtocolConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.config.capabilities import (
    PARAMETER_CAPABILITIES,
    CapabilityError,
    capability_issues,
    effective_parameter_snapshot,
    require_effective_target,
    require_executable_scenario,
    require_time_evolution,
)
from qiskit_qkd.temporal import ConstantProfile, LinearRampProfile


def _scenario(**updates: object) -> Scenario:
    values = {"pulses": 8, "clock_rate_hz": 1_000_000.0, "seed": 7}
    values.update(updates)
    return Scenario(**values)


def _decoy_source(*, scalar_mu: float | None = None) -> SourceConfig:
    return SourceConfig(
        kind="decoy_weak_coherent",
        mean_photon_number=scalar_mu,
        decoy_intensities=(
            DecoyIntensity("signal", 0.5, 0.8),
            DecoyIntensity("decoy", 0.1, 0.15),
            DecoyIntensity("vacuum", 0.0, 0.05),
        ),
    )


def test_rejects_scalar_mean_photon_number_shadowed_by_decoys() -> None:
    scenario = _scenario(source=_decoy_source(scalar_mu=0.7))

    issues = capability_issues(scenario)

    assert {issue.code for issue in issues} >= {"SOURCE_MEAN_PHOTON_NUMBER_SHADOWED"}
    with pytest.raises(CapabilityError) as exc_info:
        require_effective_target(scenario, "source.mean_photon_number")
    assert exc_info.value.issues[0].code == "TARGET_HAS_NO_EFFECT"
    assert exc_info.value.issues[0].loc == "source.mean_photon_number"


@pytest.mark.parametrize(
    ("kind", "effective"),
    [("space", False), ("free_space", True), ("satellite", True)],
)
def test_pointing_target_follows_channel_alias_capabilities(
    kind: str,
    effective: bool,
) -> None:
    scenario = _scenario(
        channel=ChannelConfig(
            kind=kind,
            distance_km=10.0,
            pointing_jitter_rad=1e-6,
        ),
    )

    if effective:
        assert require_effective_target(scenario, "channel.pointing_jitter_rad") == (
            "channel.pointing_jitter_rad"
        )
    else:
        with pytest.raises(CapabilityError) as exc_info:
            require_effective_target(scenario, "channel.pointing_jitter_rad")
        assert exc_info.value.issues[0].code == "TARGET_HAS_NO_EFFECT"
        assert any(
            issue.code == "CHANNEL_PARAMETER_IGNORED"
            for issue in capability_issues(scenario)
        )


@pytest.mark.parametrize(
    "dynamic",
    [
        DynamicConfig(),
        DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.distance_km",
                    profile=ConstantProfile(start_s=0.0, end_s=2.0, value=10.0),
                ),
            ),
        ),
    ],
)
def test_time_sweep_requires_nonconstant_effective_evolution(
    dynamic: DynamicConfig,
) -> None:
    scenario = _scenario(dynamic=dynamic)

    with pytest.raises(CapabilityError) as exc_info:
        require_time_evolution(scenario, [0.0, 1.0, 2.0])

    assert exc_info.value.issues[0].code == "TIME_EVOLUTION_REQUIRED"


def test_time_sweep_accepts_varying_schedule_over_requested_points() -> None:
    scenario = _scenario(
        channel=ChannelConfig(kind="fiber"),
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.distance_km",
                    profile=LinearRampProfile(
                        start_s=0.0,
                        end_s=2.0,
                        start_value=0.0,
                        end_value=20.0,
                    ),
                ),
            ),
        ),
    )

    assert require_time_evolution(scenario, [0.0, 1.0, 2.0]) is None


def test_time_sweep_rejects_boolean_points_as_non_numeric() -> None:
    scenario = _scenario(
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.distance_km",
                    profile=LinearRampProfile(
                        start_s=0.0,
                        end_s=2.0,
                        start_value=0.0,
                        end_value=20.0,
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(CapabilityError) as exc_info:
        require_time_evolution(scenario, [False, True])

    assert exc_info.value.issues[0].code == "TIME_POINTS_INVALID"


@pytest.mark.parametrize(
    "scenario,code",
    [
        (
            _scenario(source=SourceConfig(kind="entangled_pair")),
            "BB84_SOURCE_INCOMPATIBLE",
        ),
        (
            _scenario(protocol=ProtocolConfig(name="e91")),
            "E91_SOURCE_REQUIRED",
        ),
        (
            _scenario(
                protocol=ProtocolConfig(name="e91"),
                source=SourceConfig(kind="entangled_pair"),
                eavesdropper=EveConfig(kind="intercept_resend"),
            ),
            "E91_EAVESDROPPER_UNSUPPORTED",
        ),
    ],
)
def test_executable_scenario_rejects_protocol_model_mismatches(
    scenario: Scenario,
    code: str,
) -> None:
    with pytest.raises(CapabilityError) as exc_info:
        require_executable_scenario(scenario)

    assert code in {issue.code for issue in exc_info.value.issues}


def test_effective_snapshot_names_models_and_consumed_parameters() -> None:
    scenario = _scenario(
        source=SourceConfig(kind="weak_coherent", mean_photon_number=0.5),
        channel=ChannelConfig(
            kind="satellite",
            distance_km=10.0,
            pointing_jitter_rad=1e-6,
        ),
    )

    snapshot = effective_parameter_snapshot(scenario)

    assert snapshot["protocol_model"] == "BB84Protocol"
    assert snapshot["source_model"] == "WeakCoherentDecoySource"
    assert snapshot["channel_model"] == "FreeSpaceChannel"
    assert "source.mean_photon_number" in snapshot["consumed_parameters"]
    assert "channel.pointing_jitter_rad" in snapshot["consumed_parameters"]
    assert snapshot["effective_values"]["source.mean_photon_number"] == 0.5
    assert snapshot["effective_values"]["channel.pointing_jitter_rad"] == 1e-6
    assert "channel.attenuation_db_km" in snapshot["ignored_values"]
    assert snapshot["derived_parameters"]["effective_background_count_rate_hz"] == 0.0
    assert snapshot["derived_parameters"]["effective_jitter_std_s"] == 0.0
    assert snapshot["derived_parameters"]["channel_loss_db"] >= 0.0
    assert "chsh_s" not in snapshot["applicable_metrics"]
    json.dumps(snapshot)


def test_default_structured_e91_settings_do_not_emit_false_warnings() -> None:
    issues = capability_issues(_scenario())

    assert issues == ()


def test_neutral_placeholders_for_inapplicable_models_do_not_warn() -> None:
    scenario = _scenario(
        source=SourceConfig(kind="ideal", decoy_intensities=()),
        channel=ChannelConfig(kind="ideal", attenuation_db_km=0.0),
    )

    assert capability_issues(scenario) == ()
    with pytest.raises(CapabilityError):
        require_effective_target(scenario, "channel.attenuation_db_km")


def test_non_neutral_override_for_inapplicable_model_still_warns() -> None:
    scenario = _scenario(
        channel=ChannelConfig(kind="ideal", attenuation_db_km=0.3),
    )

    issues = capability_issues(scenario)

    assert any(issue.loc == "channel.attenuation_db_km" for issue in issues)


def test_e91_does_not_advertise_unconsumed_pdl_parameters() -> None:
    scenario = _scenario(
        protocol=ProtocolConfig(name="e91"),
        source=SourceConfig(kind="entangled_pair"),
        channel=ChannelConfig(polarization_dependent_loss_db=3.0),
    )

    with pytest.raises(CapabilityError) as exc_info:
        require_effective_target(
            scenario,
            "channel.polarization_dependent_loss_db",
        )

    assert exc_info.value.issues[0].code == "TARGET_HAS_NO_EFFECT"
    snapshot = effective_parameter_snapshot(scenario)
    assert "channel.polarization_dependent_loss_db" in snapshot["ignored_parameters"]
    assert PARAMETER_CAPABILITIES[
        "channel.polarization_dependent_loss_db"
    ].applicable_protocols == ("bb84",)


def test_pns_split_probability_requires_a_multiphoton_source() -> None:
    ideal = _scenario(
        eavesdropper=EveConfig(
            kind="photon_number_splitting",
            pns_split_probability=1.0,
        ),
    )

    with pytest.raises(CapabilityError) as exc_info:
        require_effective_target(ideal, "eavesdropper.pns_split_probability")

    assert exc_info.value.issues[0].code == "TARGET_HAS_NO_EFFECT"
    assert (
        require_effective_target(
            ideal,
            "eavesdropper.pns_block_single_photon_probability",
        )
        == "eavesdropper.pns_block_single_photon_probability"
    )

    weak_coherent = _scenario(
        source=SourceConfig(kind="weak_coherent", mean_photon_number=0.5),
        eavesdropper=EveConfig(
            kind="photon_number_splitting",
            pns_split_probability=1.0,
        ),
    )
    assert (
        require_effective_target(
            weak_coherent,
            "eavesdropper.pns_split_probability",
        )
        == "eavesdropper.pns_split_probability"
    )
    assert PARAMETER_CAPABILITIES[
        "eavesdropper.pns_split_probability"
    ].applicable_protocols == ("bb84",)


@pytest.mark.parametrize("attack_position", ["post_loss", "pre_loss"])
def test_attack_position_is_effective_only_with_an_active_bb84_eve(
    attack_position: str,
) -> None:
    no_eve = _scenario(
        eavesdropper=EveConfig(attack_position=attack_position),
    )
    no_eve_snapshot = effective_parameter_snapshot(no_eve)
    assert "eavesdropper.attack_position" in no_eve_snapshot["ignored_parameters"]
    if attack_position != "post_loss":
        assert any(
            issue.loc == "eavesdropper.attack_position"
            for issue in capability_issues(no_eve)
        )

    pns = _scenario(
        source=SourceConfig(kind="weak_coherent", mean_photon_number=0.5),
        eavesdropper=EveConfig(
            kind="photon_number_splitting",
            attack_position=attack_position,
        ),
    )
    pns_snapshot = effective_parameter_snapshot(pns)
    assert "eavesdropper.attack_position" in pns_snapshot["consumed_parameters"]
    capability = PARAMETER_CAPABILITIES["eavesdropper.attack_position"]
    assert capability.applicable_protocols == ("bb84",)
    assert "post_loss" in capability.scope
    assert "pre_loss" in capability.scope


@pytest.mark.parametrize(
    "target",
    [
        "channel.phase_damping_probability",
        "channel.polarization_rotation_z_rad",
    ],
)
def test_phase_only_channel_targets_require_the_bb84_x_basis(target: str) -> None:
    z_only = _scenario(
        protocol=ProtocolConfig(basis_choices=("Z",)),
    )

    with pytest.raises(CapabilityError) as exc_info:
        require_effective_target(z_only, target)

    assert exc_info.value.issues[0].code == "TARGET_HAS_NO_EFFECT"
    x_only = _scenario(protocol=ProtocolConfig(basis_choices=("X",)))
    assert require_effective_target(x_only, target) == target


@pytest.mark.parametrize("target", ["scenario.pulses", "scenario.clock_rate_hz"])
def test_scenario_sweep_targets_are_not_accepted_as_dynamic_schedules(
    target: str,
) -> None:
    capability = PARAMETER_CAPABILITIES[target]

    assert capability.sweepable is True
    assert capability.dynamic is False
    with pytest.raises(ValueError, match="does not support time-dependent schedules"):
        ParameterSchedule(
            target=target,
            profile=ConstantProfile(start_s=0.0, end_s=1.0, value=2.0),
        )
