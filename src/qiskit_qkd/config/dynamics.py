"""Dynamic parameter schedules for reproducible scenario variations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import reject_unknown_fields, require_non_empty_str
from qiskit_qkd.temporal.profiles import TimeProfile, profile_from_dict

_DYNAMIC_TARGETS: dict[str, set[str]] = {
    "source": {
        "emission_probability",
        "mean_photon_number",
        "preparation_error_probability",
    },
    "channel": {
        "distance_km",
        "attenuation_db_km",
        "fixed_loss_db",
        "wavelength_nm",
        "transmitter_aperture_m",
        "receiver_aperture_m",
        "beam_divergence_rad",
        "atmospheric_extinction_db_km",
        "scintillation_sigma",
        "pointing_jitter_rad",
        "underwater_extinction_m_inv",
        "underwater_scattering_broadening_ns_per_m",
        "depolarizing_probability",
        "phase_damping_probability",
        "polarization_rotation_y_rad",
        "polarization_rotation_z_rad",
        "background_count_rate_hz",
        "pmd_coefficient_ps_sqrt_km",
        "chromatic_dispersion_ps_nm_km",
        "source_spectral_width_nm",
        "polarization_dependent_loss_db",
        "classical_channel_power_mw",
        "raman_coefficient_hz_mw_km",
        "raman_filter_isolation_db",
    },
    "detector": {
        "efficiency",
        "dark_count_rate_hz",
        "gate_width_s",
        "dead_time_s",
        "afterpulse_probability",
        "readout_error_probability",
    },
    "timing": {
        "propagation_delay_s",
        "jitter_std_s",
        "clock_offset_s",
        "clock_drift_ppm",
    },
    "post_processing": {
        "qber_abort_threshold",
        "qber_sample_fraction",
        "error_correction_efficiency",
    },
    "eavesdropper": {
        "intercept_probability",
        "pns_split_probability",
        "pns_block_single_photon_probability",
    },
}

SWEEPABLE_TARGETS = frozenset(
    target
    for section, fields in _DYNAMIC_TARGETS.items()
    for target in (f"{section}.{field}" for field in fields)
) | frozenset({"scenario.pulses", "scenario.clock_rate_hz"})


def validate_parameter_target(target: str) -> str:
    """Validate a public ``section.field`` dynamic-parameter target."""

    normalized = require_non_empty_str("target", target)
    parts = normalized.split(".")
    if len(parts) != 2:
        raise ValueError("target must use 'section.field' syntax")
    section, field = parts
    if normalized not in SWEEPABLE_TARGETS:
        raise ValueError(f"Unsupported dynamic parameter target: {normalized!r}")
    return normalized


@dataclass(frozen=True, slots=True)
class ParameterSchedule:
    """Bind one dynamic parameter target to a finite time profile."""

    target: str
    profile: TimeProfile

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", validate_parameter_target(self.target))
        if isinstance(self.profile, Mapping):
            object.__setattr__(self, "profile", profile_from_dict(self.profile))
        elif not hasattr(self.profile, "value_at") or not hasattr(
            self.profile,
            "to_dict",
        ):
            raise TypeError("profile must be a time profile")

    def value_at(self, time_s: float) -> float | None:
        return self.profile.value_at(time_s)

    def to_dict(self) -> JSONObject:
        return {"target": self.target, "profile": self.profile.to_dict()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields("ParameterSchedule", data, {"target", "profile"})
        return cls(
            target=data["target"],
            profile=profile_from_dict(data["profile"]),
        )


@dataclass(frozen=True, slots=True)
class DynamicConfig:
    """Optional time-dependent parameter schedules attached to a scenario."""

    parameter_schedules: tuple[ParameterSchedule, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.parameter_schedules, tuple | list):
            raise TypeError("parameter_schedules must be a tuple or list")
        schedules: list[ParameterSchedule] = []
        for index, schedule in enumerate(self.parameter_schedules):
            if isinstance(schedule, ParameterSchedule):
                schedules.append(schedule)
            elif isinstance(schedule, Mapping):
                schedules.append(ParameterSchedule.from_dict(schedule))
            else:
                raise TypeError(f"parameter_schedules[{index}] must be a schedule")
        object.__setattr__(self, "parameter_schedules", tuple(schedules))

    def to_dict(self) -> JSONObject:
        return {
            "parameter_schedules": [
                schedule.to_dict() for schedule in self.parameter_schedules
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields("DynamicConfig", data, {"parameter_schedules"})
        return cls(
            parameter_schedules=tuple(
                ParameterSchedule.from_dict(schedule)
                for schedule in data.get("parameter_schedules", [])
            ),
        )
