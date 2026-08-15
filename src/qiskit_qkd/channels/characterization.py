"""Channel-state characterization helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import require_non_negative_number
from qiskit_qkd.config import Scenario
from qiskit_qkd.temporal import ParameterResolver

from .factory import ConcreteChannel, channel_from_config
from .impairments import (
    chromatic_broadening_s,
    effective_background_count_rate_hz,
    effective_jitter_std_s,
    pdl_min_transmittance,
    pmd_broadening_s,
    raman_count_rate_hz,
    scattering_broadening_s,
    temporal_broadening_s,
)


@dataclass(frozen=True, slots=True)
class ChannelState:
    """Physical and noise state of the configured communication channel."""

    time_s: float
    channel_kind: str
    distance_km: float
    attenuation_db_km: float
    fixed_loss_db: float
    wavelength_nm: float
    transmitter_aperture_m: float
    receiver_aperture_m: float
    beam_divergence_rad: float
    effective_beam_divergence_rad: float
    geometric_transmittance: float
    atmospheric_extinction_db_km: float
    atmospheric_loss_db: float
    scintillation_sigma: float
    pointing_jitter_rad: float
    underwater_extinction_m_inv: float
    underwater_scattering_broadening_ns_per_m: float
    loss_db: float
    transmittance: float
    depolarizing_probability: float
    phase_damping_probability: float
    polarization_rotation_y_rad: float
    polarization_rotation_z_rad: float
    background_count_rate_hz: float
    pmd_coefficient_ps_sqrt_km: float
    chromatic_dispersion_ps_nm_km: float
    source_spectral_width_nm: float
    pmd_broadening_s: float
    chromatic_broadening_s: float
    scattering_broadening_s: float
    temporal_broadening_s: float
    effective_jitter_std_s: float
    polarization_dependent_loss_db: float
    pdl_axis_basis: str
    pdl_axis_bit: int
    pdl_min_transmittance: float
    classical_channel_power_mw: float
    raman_coefficient_hz_mw_km: float
    raman_filter_isolation_db: float
    raman_count_rate_hz: float
    effective_background_count_rate_hz: float

    def to_dict(self) -> JSONObject:
        return {
            "time_s": self.time_s,
            "channel_kind": self.channel_kind,
            "distance_km": self.distance_km,
            "attenuation_db_km": self.attenuation_db_km,
            "fixed_loss_db": self.fixed_loss_db,
            "wavelength_nm": self.wavelength_nm,
            "transmitter_aperture_m": self.transmitter_aperture_m,
            "receiver_aperture_m": self.receiver_aperture_m,
            "beam_divergence_rad": self.beam_divergence_rad,
            "effective_beam_divergence_rad": self.effective_beam_divergence_rad,
            "geometric_transmittance": self.geometric_transmittance,
            "atmospheric_extinction_db_km": self.atmospheric_extinction_db_km,
            "atmospheric_loss_db": self.atmospheric_loss_db,
            "scintillation_sigma": self.scintillation_sigma,
            "pointing_jitter_rad": self.pointing_jitter_rad,
            "underwater_extinction_m_inv": self.underwater_extinction_m_inv,
            "underwater_scattering_broadening_ns_per_m": (
                self.underwater_scattering_broadening_ns_per_m
            ),
            "loss_db": self.loss_db,
            "transmittance": self.transmittance,
            "depolarizing_probability": self.depolarizing_probability,
            "phase_damping_probability": self.phase_damping_probability,
            "polarization_rotation_y_rad": self.polarization_rotation_y_rad,
            "polarization_rotation_z_rad": self.polarization_rotation_z_rad,
            "background_count_rate_hz": self.background_count_rate_hz,
            "pmd_coefficient_ps_sqrt_km": self.pmd_coefficient_ps_sqrt_km,
            "chromatic_dispersion_ps_nm_km": self.chromatic_dispersion_ps_nm_km,
            "source_spectral_width_nm": self.source_spectral_width_nm,
            "pmd_broadening_s": self.pmd_broadening_s,
            "chromatic_broadening_s": self.chromatic_broadening_s,
            "scattering_broadening_s": self.scattering_broadening_s,
            "temporal_broadening_s": self.temporal_broadening_s,
            "effective_jitter_std_s": self.effective_jitter_std_s,
            "polarization_dependent_loss_db": self.polarization_dependent_loss_db,
            "pdl_axis_basis": self.pdl_axis_basis,
            "pdl_axis_bit": self.pdl_axis_bit,
            "pdl_min_transmittance": self.pdl_min_transmittance,
            "classical_channel_power_mw": self.classical_channel_power_mw,
            "raman_coefficient_hz_mw_km": self.raman_coefficient_hz_mw_km,
            "raman_filter_isolation_db": self.raman_filter_isolation_db,
            "raman_count_rate_hz": self.raman_count_rate_hz,
            "effective_background_count_rate_hz": (
                self.effective_background_count_rate_hz
            ),
        }


def channel_state_from_scenario(
    scenario: Scenario,
    *,
    time_s: float = 0.0,
    resolver: ParameterResolver | None = None,
) -> ChannelState:
    """Return the effective channel state at ``time_s``."""

    time = require_non_negative_number("time_s", time_s)
    active_resolver = resolver or ParameterResolver()
    effective = active_resolver.scenario_at(scenario, time_s=time)
    return _channel_state_from_effective(effective, time_s=time)


@dataclass(frozen=True, slots=True)
class ChannelCharacterizer:
    """Create JSON-safe channel characterization rows."""

    resolver: ParameterResolver = ParameterResolver()

    def characterize_time(
        self,
        scenario: Scenario,
        *,
        time_points_s: Iterable[float],
    ) -> list[JSONObject]:
        """Return channel-state rows for selected times."""

        rows: list[JSONObject] = []
        for time_s in time_points_s:
            time = require_non_negative_number("time_s", time_s)
            effective = self.resolver.scenario_at(scenario, time_s=time)
            row = _channel_state_from_effective(effective, time_s=time).to_dict()
            row.update(self.resolver.parameter_values(scenario, time_s=time))
            rows.append(row)
        return rows

    def characterize_distance(
        self,
        scenario: Scenario,
        *,
        distances_km: Iterable[float],
        time_s: float = 0.0,
    ) -> list[JSONObject]:
        """Return channel-state rows for selected fiber distances."""

        time = require_non_negative_number("time_s", time_s)
        effective = self.resolver.scenario_at(scenario, time_s=time)
        rows: list[JSONObject] = []
        for distance_km in distances_km:
            distance = require_non_negative_number("distance_km", distance_km)
            distance_scenario = replace(
                effective,
                channel=replace(effective.channel, distance_km=distance),
            )
            row = _channel_state_from_effective(
                distance_scenario,
                time_s=time,
            ).to_dict()
            dynamic_values = self.resolver.parameter_values(
                scenario,
                time_s=time,
            )
            if "channel.distance_km" in dynamic_values:
                dynamic_values["channel.distance_km"] = distance
            row.update(dynamic_values)
            rows.append(row)
        return rows


def _channel_state_from_effective(scenario: Scenario, *, time_s: float) -> ChannelState:
    channel = channel_from_config(scenario.channel)
    return ChannelState(
        time_s=time_s,
        channel_kind=scenario.channel.kind,
        distance_km=scenario.channel.distance_km,
        attenuation_db_km=scenario.channel.attenuation_db_km,
        fixed_loss_db=scenario.channel.fixed_loss_db,
        wavelength_nm=scenario.channel.wavelength_nm,
        transmitter_aperture_m=scenario.channel.transmitter_aperture_m,
        receiver_aperture_m=scenario.channel.receiver_aperture_m,
        beam_divergence_rad=scenario.channel.beam_divergence_rad,
        effective_beam_divergence_rad=_effective_beam_divergence_rad(channel),
        geometric_transmittance=_geometric_transmittance(channel),
        atmospheric_extinction_db_km=scenario.channel.atmospheric_extinction_db_km,
        atmospheric_loss_db=_atmospheric_loss_db(channel),
        scintillation_sigma=scenario.channel.scintillation_sigma,
        pointing_jitter_rad=scenario.channel.pointing_jitter_rad,
        underwater_extinction_m_inv=scenario.channel.underwater_extinction_m_inv,
        underwater_scattering_broadening_ns_per_m=(
            scenario.channel.underwater_scattering_broadening_ns_per_m
        ),
        loss_db=channel.loss_db,
        transmittance=channel.transmittance(),
        depolarizing_probability=scenario.channel.depolarizing_probability,
        phase_damping_probability=scenario.channel.phase_damping_probability,
        polarization_rotation_y_rad=scenario.channel.polarization_rotation_y_rad,
        polarization_rotation_z_rad=scenario.channel.polarization_rotation_z_rad,
        background_count_rate_hz=scenario.channel.background_count_rate_hz,
        pmd_coefficient_ps_sqrt_km=(
            scenario.channel.pmd_coefficient_ps_sqrt_km
        ),
        chromatic_dispersion_ps_nm_km=(
            scenario.channel.chromatic_dispersion_ps_nm_km
        ),
        source_spectral_width_nm=scenario.channel.source_spectral_width_nm,
        pmd_broadening_s=pmd_broadening_s(scenario.channel),
        chromatic_broadening_s=chromatic_broadening_s(scenario.channel),
        scattering_broadening_s=scattering_broadening_s(scenario.channel),
        temporal_broadening_s=temporal_broadening_s(scenario.channel),
        effective_jitter_std_s=effective_jitter_std_s(scenario),
        polarization_dependent_loss_db=(
            scenario.channel.polarization_dependent_loss_db
        ),
        pdl_axis_basis=scenario.channel.pdl_axis_basis,
        pdl_axis_bit=scenario.channel.pdl_axis_bit,
        pdl_min_transmittance=pdl_min_transmittance(channel, scenario.channel),
        classical_channel_power_mw=scenario.channel.classical_channel_power_mw,
        raman_coefficient_hz_mw_km=scenario.channel.raman_coefficient_hz_mw_km,
        raman_filter_isolation_db=scenario.channel.raman_filter_isolation_db,
        raman_count_rate_hz=raman_count_rate_hz(scenario.channel),
        effective_background_count_rate_hz=effective_background_count_rate_hz(
            scenario.channel,
        ),
    )

def _effective_beam_divergence_rad(channel: ConcreteChannel) -> float:
    return float(getattr(channel, "divergence_rad", 0.0))


def _geometric_transmittance(channel: ConcreteChannel) -> float:
    return float(getattr(channel, "geometric_transmittance", 1.0))


def _atmospheric_loss_db(channel: ConcreteChannel) -> float:
    return float(getattr(channel, "atmospheric_loss_db", 0.0))
