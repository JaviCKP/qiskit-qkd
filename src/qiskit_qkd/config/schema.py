"""Validated configuration objects for reproducible QKD scenarios."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from qiskit_qkd._json import JSONObject, dumps_canonical, dumps_pretty, loads_object
from qiskit_qkd._validation import (
    normalize_metadata,
    normalize_string_tuple,
    reject_unknown_fields,
    require_bool,
    require_choice,
    require_finite_number,
    require_minimum_number,
    require_non_empty_str,
    require_non_negative_int,
    require_non_negative_number,
    require_optional_probability,
    require_positive_int,
    require_positive_number,
    require_probability,
)
from qiskit_qkd.reproducibility import sample_unit_interval

from .dynamics import DynamicConfig

SCHEMA_VERSION = 1
SLOT_ASSIGNMENT_POLICIES = {"discard", "nearest"}
PROTOCOL_NAMES = {"bb84", "e91"}
BB84_BASIS_CHOICES = {"Z", "X"}
SOURCE_KINDS = {
    "ideal",
    "ideal_single_photon",
    "single_photon",
    "weak_coherent",
    "decoy_weak_coherent",
    "entangled_pair",
    "bell_pair",
    "e91",
}
CHANNEL_KINDS = {
    "ideal",
    "fiber",
    "space",
    "deep_space",
    "vacuum",
    "free_space",
    "atmospheric",
    "satellite",
    "underwater",
    "water",
    "marine",
}
DETECTOR_KINDS = {"ideal", "threshold"}
DECOY_SECURITY_METHODS = {"none", "vacuum_weak_asymptotic"}
E91_BELL_STATES = {"psi_minus", "phi_plus"}
E91_DEFAULT_ALICE_ANGLES_RAD = (0.0, math.pi / 2.0)
E91_DEFAULT_BOB_ANGLES_RAD = (math.pi / 4.0, -math.pi / 4.0, 0.0)
E91_DEFAULT_KEY_SETTING_PAIRS = ((0, 2),)
E91_DEFAULT_CHSH_TERMS = ((0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, -1))
PROBABILITY_SUM_TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class ProtocolConfig:
    """Protocol-level configuration for a QKD scenario."""

    name: str = "bb84"
    basis_choices: tuple[str, ...] = ("Z", "X")

    def __post_init__(self) -> None:
        name = require_non_empty_str("name", self.name).lower()
        object.__setattr__(self, "name", require_choice("name", name, PROTOCOL_NAMES))
        basis_choices = tuple(
            basis.upper()
            for basis in normalize_string_tuple(
                "basis_choices",
                self.basis_choices,
            )
        )
        if any(basis not in BB84_BASIS_CHOICES for basis in basis_choices):
            raise ValueError("basis_choices must contain only Z and X")
        if len(set(basis_choices)) != len(basis_choices):
            raise ValueError("basis_choices must not contain duplicate bases")
        object.__setattr__(self, "basis_choices", basis_choices)

    def to_dict(self) -> JSONObject:
        return {"name": self.name, "basis_choices": list(self.basis_choices)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields("ProtocolConfig", data, {"name", "basis_choices"})
        return cls(
            name=data.get("name", "bb84"),
            basis_choices=tuple(data.get("basis_choices", ("Z", "X"))),
        )


@dataclass(frozen=True, slots=True)
class DecoyIntensity:
    """Weak-coherent decoy intensity class."""

    name: str
    mean_photon_number: float
    selection_probability: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_non_empty_str("name", self.name))
        object.__setattr__(
            self,
            "mean_photon_number",
            require_non_negative_number(
                "mean_photon_number",
                self.mean_photon_number,
            ),
        )
        object.__setattr__(
            self,
            "selection_probability",
            require_probability(
                "selection_probability",
                self.selection_probability,
            ),
        )

    def to_dict(self) -> JSONObject:
        return {
            "name": self.name,
            "mean_photon_number": self.mean_photon_number,
            "selection_probability": self.selection_probability,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "DecoyIntensity",
            data,
            {"name", "mean_photon_number", "selection_probability"},
        )
        return cls(
            name=data["name"],
            mean_photon_number=data["mean_photon_number"],
            selection_probability=data["selection_probability"],
        )


def _normalize_decoy_intensities(
    value: tuple[DecoyIntensity, ...] | list[DecoyIntensity | Mapping[str, Any]],
) -> tuple[DecoyIntensity, ...]:
    if not isinstance(value, tuple | list):
        raise TypeError("decoy_intensities must be a tuple or list")
    intensities: list[DecoyIntensity] = []
    names: set[str] = set()
    for index, item in enumerate(value):
        if isinstance(item, DecoyIntensity):
            intensity = item
        elif isinstance(item, Mapping):
            intensity = DecoyIntensity.from_dict(item)
        else:
            raise TypeError(f"decoy_intensities[{index}] must be a DecoyIntensity")
        if intensity.name in names:
            raise ValueError("decoy_intensity names must be unique")
        names.add(intensity.name)
        intensities.append(intensity)
    if intensities:
        total = sum(intensity.selection_probability for intensity in intensities)
        if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise ValueError("decoy selection probabilities must sum to 1")
    return tuple(intensities)


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Source configuration with explicit emission probabilities."""

    kind: str = "ideal_single_photon"
    emission_probability: float = 1.0
    mean_photon_number: float | None = None
    preparation_error_probability: float = 0.0
    decoy_intensities: tuple[DecoyIntensity, ...] = ()

    def __post_init__(self) -> None:
        kind = require_non_empty_str("kind", self.kind).lower()
        object.__setattr__(
            self,
            "kind",
            require_choice("kind", kind, SOURCE_KINDS),
        )
        object.__setattr__(
            self,
            "emission_probability",
            require_probability("emission_probability", self.emission_probability),
        )
        if self.mean_photon_number is not None:
            object.__setattr__(
                self,
                "mean_photon_number",
                require_non_negative_number(
                    "mean_photon_number",
                    self.mean_photon_number,
                ),
            )
        object.__setattr__(
            self,
            "preparation_error_probability",
            require_probability(
                "preparation_error_probability",
                self.preparation_error_probability,
            ),
        )
        object.__setattr__(
            self,
            "decoy_intensities",
            _normalize_decoy_intensities(self.decoy_intensities),
        )
        if (
            kind in {"weak_coherent", "decoy_weak_coherent"}
            and not self.decoy_intensities
            and self.mean_photon_number is None
        ):
            raise ValueError(
                "weak_coherent sources require mean_photon_number when "
                "decoy_intensities is empty",
            )

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind,
            "emission_probability": self.emission_probability,
            "mean_photon_number": self.mean_photon_number,
            "preparation_error_probability": self.preparation_error_probability,
            "decoy_intensities": [
                intensity.to_dict() for intensity in self.decoy_intensities
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "SourceConfig",
            data,
            {
                "kind",
                "emission_probability",
                "mean_photon_number",
                "preparation_error_probability",
                "decoy_intensities",
            },
        )
        return cls(
            kind=data.get("kind", "ideal_single_photon"),
            emission_probability=data.get("emission_probability", 1.0),
            mean_photon_number=data.get("mean_photon_number"),
            preparation_error_probability=data.get(
                "preparation_error_probability",
                0.0,
            ),
            decoy_intensities=tuple(data.get("decoy_intensities", ())),
        )


@dataclass(frozen=True, slots=True)
class ChannelConfig:
    """Physical channel parameters with distance and loss units in field names."""

    kind: str = "ideal"
    distance_km: float = 0.0
    attenuation_db_km: float = 0.2
    fixed_loss_db: float = 0.0
    wavelength_nm: float = 850.0
    transmitter_aperture_m: float = 0.10
    receiver_aperture_m: float = 0.50
    beam_divergence_rad: float = 0.0
    atmospheric_extinction_db_km: float = 0.0
    scintillation_sigma: float = 0.0
    pointing_jitter_rad: float = 0.0
    underwater_extinction_m_inv: float = 0.0
    underwater_scattering_broadening_ns_per_m: float = 0.0
    depolarizing_probability: float = 0.0
    phase_damping_probability: float = 0.0
    polarization_rotation_y_rad: float = 0.0
    polarization_rotation_z_rad: float = 0.0
    background_count_rate_hz: float = 0.0
    pmd_coefficient_ps_sqrt_km: float = 0.0
    chromatic_dispersion_ps_nm_km: float = 0.0
    source_spectral_width_nm: float = 0.0
    polarization_dependent_loss_db: float = 0.0
    pdl_axis_basis: str = "Z"
    pdl_axis_bit: int = 0
    classical_channel_power_mw: float = 0.0
    raman_coefficient_hz_mw_km: float = 0.0
    raman_filter_isolation_db: float = 0.0

    def __post_init__(self) -> None:
        kind = require_non_empty_str("kind", self.kind).lower()
        object.__setattr__(
            self,
            "kind",
            require_choice("kind", kind, CHANNEL_KINDS),
        )
        object.__setattr__(
            self,
            "distance_km",
            require_non_negative_number("distance_km", self.distance_km),
        )
        object.__setattr__(
            self,
            "attenuation_db_km",
            require_non_negative_number(
                "attenuation_db_km",
                self.attenuation_db_km,
            ),
        )
        object.__setattr__(
            self,
            "fixed_loss_db",
            require_non_negative_number("fixed_loss_db", self.fixed_loss_db),
        )
        object.__setattr__(
            self,
            "wavelength_nm",
            require_positive_number("wavelength_nm", self.wavelength_nm),
        )
        object.__setattr__(
            self,
            "transmitter_aperture_m",
            require_positive_number(
                "transmitter_aperture_m",
                self.transmitter_aperture_m,
            ),
        )
        object.__setattr__(
            self,
            "receiver_aperture_m",
            require_positive_number(
                "receiver_aperture_m",
                self.receiver_aperture_m,
            ),
        )
        object.__setattr__(
            self,
            "beam_divergence_rad",
            require_non_negative_number(
                "beam_divergence_rad",
                self.beam_divergence_rad,
            ),
        )
        object.__setattr__(
            self,
            "atmospheric_extinction_db_km",
            require_non_negative_number(
                "atmospheric_extinction_db_km",
                self.atmospheric_extinction_db_km,
            ),
        )
        object.__setattr__(
            self,
            "scintillation_sigma",
            require_non_negative_number(
                "scintillation_sigma",
                self.scintillation_sigma,
            ),
        )
        object.__setattr__(
            self,
            "pointing_jitter_rad",
            require_non_negative_number(
                "pointing_jitter_rad",
                self.pointing_jitter_rad,
            ),
        )
        object.__setattr__(
            self,
            "underwater_extinction_m_inv",
            require_non_negative_number(
                "underwater_extinction_m_inv",
                self.underwater_extinction_m_inv,
            ),
        )
        object.__setattr__(
            self,
            "underwater_scattering_broadening_ns_per_m",
            require_non_negative_number(
                "underwater_scattering_broadening_ns_per_m",
                self.underwater_scattering_broadening_ns_per_m,
            ),
        )
        object.__setattr__(
            self,
            "depolarizing_probability",
            require_probability(
                "depolarizing_probability",
                self.depolarizing_probability,
            ),
        )
        object.__setattr__(
            self,
            "phase_damping_probability",
            require_probability(
                "phase_damping_probability",
                self.phase_damping_probability,
            ),
        )
        object.__setattr__(
            self,
            "polarization_rotation_y_rad",
            require_finite_number(
                "polarization_rotation_y_rad",
                self.polarization_rotation_y_rad,
            ),
        )
        object.__setattr__(
            self,
            "polarization_rotation_z_rad",
            require_finite_number(
                "polarization_rotation_z_rad",
                self.polarization_rotation_z_rad,
            ),
        )
        object.__setattr__(
            self,
            "background_count_rate_hz",
            require_non_negative_number(
                "background_count_rate_hz",
                self.background_count_rate_hz,
            ),
        )
        object.__setattr__(
            self,
            "pmd_coefficient_ps_sqrt_km",
            require_non_negative_number(
                "pmd_coefficient_ps_sqrt_km",
                self.pmd_coefficient_ps_sqrt_km,
            ),
        )
        object.__setattr__(
            self,
            "chromatic_dispersion_ps_nm_km",
            require_finite_number(
                "chromatic_dispersion_ps_nm_km",
                self.chromatic_dispersion_ps_nm_km,
            ),
        )
        object.__setattr__(
            self,
            "source_spectral_width_nm",
            require_non_negative_number(
                "source_spectral_width_nm",
                self.source_spectral_width_nm,
            ),
        )
        object.__setattr__(
            self,
            "polarization_dependent_loss_db",
            require_non_negative_number(
                "polarization_dependent_loss_db",
                self.polarization_dependent_loss_db,
            ),
        )
        pdl_axis_basis = require_non_empty_str(
            "pdl_axis_basis",
            self.pdl_axis_basis,
        ).upper()
        object.__setattr__(
            self,
            "pdl_axis_basis",
            require_choice("pdl_axis_basis", pdl_axis_basis, {"Z", "X"}),
        )
        pdl_axis_bit = require_non_negative_int("pdl_axis_bit", self.pdl_axis_bit)
        if pdl_axis_bit not in {0, 1}:
            raise ValueError("pdl_axis_bit must be 0 or 1")
        object.__setattr__(self, "pdl_axis_bit", pdl_axis_bit)
        object.__setattr__(
            self,
            "classical_channel_power_mw",
            require_non_negative_number(
                "classical_channel_power_mw",
                self.classical_channel_power_mw,
            ),
        )
        object.__setattr__(
            self,
            "raman_coefficient_hz_mw_km",
            require_non_negative_number(
                "raman_coefficient_hz_mw_km",
                self.raman_coefficient_hz_mw_km,
            ),
        )
        object.__setattr__(
            self,
            "raman_filter_isolation_db",
            require_non_negative_number(
                "raman_filter_isolation_db",
                self.raman_filter_isolation_db,
            ),
        )

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind,
            "distance_km": self.distance_km,
            "attenuation_db_km": self.attenuation_db_km,
            "fixed_loss_db": self.fixed_loss_db,
            "wavelength_nm": self.wavelength_nm,
            "transmitter_aperture_m": self.transmitter_aperture_m,
            "receiver_aperture_m": self.receiver_aperture_m,
            "beam_divergence_rad": self.beam_divergence_rad,
            "atmospheric_extinction_db_km": self.atmospheric_extinction_db_km,
            "scintillation_sigma": self.scintillation_sigma,
            "pointing_jitter_rad": self.pointing_jitter_rad,
            "underwater_extinction_m_inv": self.underwater_extinction_m_inv,
            "underwater_scattering_broadening_ns_per_m": (
                self.underwater_scattering_broadening_ns_per_m
            ),
            "depolarizing_probability": self.depolarizing_probability,
            "phase_damping_probability": self.phase_damping_probability,
            "polarization_rotation_y_rad": self.polarization_rotation_y_rad,
            "polarization_rotation_z_rad": self.polarization_rotation_z_rad,
            "background_count_rate_hz": self.background_count_rate_hz,
            "pmd_coefficient_ps_sqrt_km": self.pmd_coefficient_ps_sqrt_km,
            "chromatic_dispersion_ps_nm_km": self.chromatic_dispersion_ps_nm_km,
            "source_spectral_width_nm": self.source_spectral_width_nm,
            "polarization_dependent_loss_db": self.polarization_dependent_loss_db,
            "pdl_axis_basis": self.pdl_axis_basis,
            "pdl_axis_bit": self.pdl_axis_bit,
            "classical_channel_power_mw": self.classical_channel_power_mw,
            "raman_coefficient_hz_mw_km": self.raman_coefficient_hz_mw_km,
            "raman_filter_isolation_db": self.raman_filter_isolation_db,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "ChannelConfig",
            data,
            {
                "kind",
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
                "pdl_axis_basis",
                "pdl_axis_bit",
                "classical_channel_power_mw",
                "raman_coefficient_hz_mw_km",
                "raman_filter_isolation_db",
            },
        )
        return cls(
            kind=data.get("kind", "ideal"),
            distance_km=data.get("distance_km", 0.0),
            attenuation_db_km=data.get("attenuation_db_km", 0.2),
            fixed_loss_db=data.get("fixed_loss_db", 0.0),
            wavelength_nm=data.get("wavelength_nm", 850.0),
            transmitter_aperture_m=data.get("transmitter_aperture_m", 0.10),
            receiver_aperture_m=data.get("receiver_aperture_m", 0.50),
            beam_divergence_rad=data.get("beam_divergence_rad", 0.0),
            atmospheric_extinction_db_km=data.get(
                "atmospheric_extinction_db_km",
                0.0,
            ),
            scintillation_sigma=data.get("scintillation_sigma", 0.0),
            pointing_jitter_rad=data.get("pointing_jitter_rad", 0.0),
            underwater_extinction_m_inv=data.get("underwater_extinction_m_inv", 0.0),
            underwater_scattering_broadening_ns_per_m=data.get(
                "underwater_scattering_broadening_ns_per_m",
                0.0,
            ),
            depolarizing_probability=data.get("depolarizing_probability", 0.0),
            phase_damping_probability=data.get("phase_damping_probability", 0.0),
            polarization_rotation_y_rad=data.get("polarization_rotation_y_rad", 0.0),
            polarization_rotation_z_rad=data.get("polarization_rotation_z_rad", 0.0),
            background_count_rate_hz=data.get("background_count_rate_hz", 0.0),
            pmd_coefficient_ps_sqrt_km=data.get("pmd_coefficient_ps_sqrt_km", 0.0),
            chromatic_dispersion_ps_nm_km=data.get(
                "chromatic_dispersion_ps_nm_km",
                0.0,
            ),
            source_spectral_width_nm=data.get("source_spectral_width_nm", 0.0),
            polarization_dependent_loss_db=data.get(
                "polarization_dependent_loss_db",
                0.0,
            ),
            pdl_axis_basis=data.get("pdl_axis_basis", "Z"),
            pdl_axis_bit=data.get("pdl_axis_bit", 0),
            classical_channel_power_mw=data.get("classical_channel_power_mw", 0.0),
            raman_coefficient_hz_mw_km=data.get(
                "raman_coefficient_hz_mw_km",
                0.0,
            ),
            raman_filter_isolation_db=data.get("raman_filter_isolation_db", 0.0),
        )


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Detector configuration with timing, efficiency, and readout parameters."""

    kind: str = "ideal"
    efficiency: float = 1.0
    dark_count_rate_hz: float = 0.0
    gate_width_s: float = 1e-9
    dead_time_s: float = 0.0
    afterpulse_probability: float = 0.0
    readout_error_probability: float = 0.0
    double_click_policy: str = "discard"

    def __post_init__(self) -> None:
        kind = require_non_empty_str("kind", self.kind).lower()
        object.__setattr__(
            self,
            "kind",
            require_choice("kind", kind, DETECTOR_KINDS),
        )
        object.__setattr__(
            self,
            "efficiency",
            require_probability("efficiency", self.efficiency),
        )
        object.__setattr__(
            self,
            "dark_count_rate_hz",
            require_non_negative_number(
                "dark_count_rate_hz",
                self.dark_count_rate_hz,
            ),
        )
        object.__setattr__(
            self,
            "gate_width_s",
            require_positive_number("gate_width_s", self.gate_width_s),
        )
        object.__setattr__(
            self,
            "dead_time_s",
            require_non_negative_number("dead_time_s", self.dead_time_s),
        )
        object.__setattr__(
            self,
            "afterpulse_probability",
            require_probability(
                "afterpulse_probability",
                self.afterpulse_probability,
            ),
        )
        object.__setattr__(
            self,
            "readout_error_probability",
            require_probability(
                "readout_error_probability",
                self.readout_error_probability,
            ),
        )
        object.__setattr__(
            self,
            "double_click_policy",
            require_non_empty_str("double_click_policy", self.double_click_policy),
        )
        if self.double_click_policy not in {"discard", "random", "error"}:
            raise ValueError("double_click_policy must be discard, random, or error")

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind,
            "efficiency": self.efficiency,
            "dark_count_rate_hz": self.dark_count_rate_hz,
            "gate_width_s": self.gate_width_s,
            "dead_time_s": self.dead_time_s,
            "afterpulse_probability": self.afterpulse_probability,
            "readout_error_probability": self.readout_error_probability,
            "double_click_policy": self.double_click_policy,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "DetectorConfig",
            data,
            {
                "kind",
                "efficiency",
                "dark_count_rate_hz",
                "gate_width_s",
                "dead_time_s",
                "afterpulse_probability",
                "readout_error_probability",
                "double_click_policy",
            },
        )
        return cls(
            kind=data.get("kind", "ideal"),
            efficiency=data.get("efficiency", 1.0),
            dark_count_rate_hz=data.get("dark_count_rate_hz", 0.0),
            gate_width_s=data.get("gate_width_s", 1e-9),
            dead_time_s=data.get("dead_time_s", 0.0),
            afterpulse_probability=data.get("afterpulse_probability", 0.0),
            readout_error_probability=data.get("readout_error_probability", 0.0),
            double_click_policy=data.get("double_click_policy", "discard"),
        )


@dataclass(frozen=True, slots=True)
class TimingConfig:
    """Clock synchronization and gate-assignment parameters."""

    propagation_delay_s: float = 0.0
    jitter_std_s: float = 0.0
    clock_offset_s: float = 0.0
    clock_drift_ppm: float = 0.0
    slot_assignment_policy: str = "discard"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "propagation_delay_s",
            require_non_negative_number(
                "propagation_delay_s",
                self.propagation_delay_s,
            ),
        )
        object.__setattr__(
            self,
            "jitter_std_s",
            require_non_negative_number("jitter_std_s", self.jitter_std_s),
        )
        object.__setattr__(
            self,
            "clock_offset_s",
            require_finite_number("clock_offset_s", self.clock_offset_s),
        )
        drift = require_finite_number("clock_drift_ppm", self.clock_drift_ppm)
        if drift <= -1_000_000.0:
            raise ValueError("clock_drift_ppm must keep Bob's slot period positive")
        object.__setattr__(self, "clock_drift_ppm", drift)
        object.__setattr__(
            self,
            "slot_assignment_policy",
            require_choice(
                "slot_assignment_policy",
                self.slot_assignment_policy,
                SLOT_ASSIGNMENT_POLICIES,
            ),
        )

    def to_dict(self) -> JSONObject:
        return {
            "propagation_delay_s": self.propagation_delay_s,
            "jitter_std_s": self.jitter_std_s,
            "clock_offset_s": self.clock_offset_s,
            "clock_drift_ppm": self.clock_drift_ppm,
            "slot_assignment_policy": self.slot_assignment_policy,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "TimingConfig",
            data,
            {
                "propagation_delay_s",
                "jitter_std_s",
                "clock_offset_s",
                "clock_drift_ppm",
                "slot_assignment_policy",
            },
        )
        return cls(
            propagation_delay_s=data.get("propagation_delay_s", 0.0),
            jitter_std_s=data.get("jitter_std_s", 0.0),
            clock_offset_s=data.get("clock_offset_s", 0.0),
            clock_drift_ppm=data.get("clock_drift_ppm", 0.0),
            slot_assignment_policy=data.get("slot_assignment_policy", "discard"),
        )


@dataclass(frozen=True, slots=True)
class PostProcessingConfig:
    """Classical post-processing parameters used after measurement."""

    sifting_enabled: bool = True
    qber_abort_threshold: float | None = 0.11
    qber_sample_fraction: float = 0.0
    error_correction_efficiency: float = 1.0
    reconciliation_block_size: int = 8
    privacy_amplification_enabled: bool = False
    decoy_security_estimation_enabled: bool = True
    decoy_security_method: str = "vacuum_weak_asymptotic"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sifting_enabled",
            require_bool("sifting_enabled", self.sifting_enabled),
        )
        object.__setattr__(
            self,
            "qber_abort_threshold",
            require_optional_probability(
                "qber_abort_threshold",
                self.qber_abort_threshold,
            ),
        )
        object.__setattr__(
            self,
            "qber_sample_fraction",
            require_probability("qber_sample_fraction", self.qber_sample_fraction),
        )
        object.__setattr__(
            self,
            "error_correction_efficiency",
            require_minimum_number(
                "error_correction_efficiency",
                self.error_correction_efficiency,
                1.0,
            ),
        )
        object.__setattr__(
            self,
            "reconciliation_block_size",
            require_positive_int(
                "reconciliation_block_size",
                self.reconciliation_block_size,
            ),
        )
        object.__setattr__(
            self,
            "privacy_amplification_enabled",
            require_bool(
                "privacy_amplification_enabled",
                self.privacy_amplification_enabled,
            ),
        )
        object.__setattr__(
            self,
            "decoy_security_estimation_enabled",
            require_bool(
                "decoy_security_estimation_enabled",
                self.decoy_security_estimation_enabled,
            ),
        )
        object.__setattr__(
            self,
            "decoy_security_method",
            require_choice(
                "decoy_security_method",
                self.decoy_security_method,
                DECOY_SECURITY_METHODS,
            ),
        )

    def to_dict(self) -> JSONObject:
        return {
            "sifting_enabled": self.sifting_enabled,
            "qber_abort_threshold": self.qber_abort_threshold,
            "qber_sample_fraction": self.qber_sample_fraction,
            "error_correction_efficiency": self.error_correction_efficiency,
            "reconciliation_block_size": self.reconciliation_block_size,
            "privacy_amplification_enabled": self.privacy_amplification_enabled,
            "decoy_security_estimation_enabled": (
                self.decoy_security_estimation_enabled
            ),
            "decoy_security_method": self.decoy_security_method,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "PostProcessingConfig",
            data,
            {
                "sifting_enabled",
                "qber_abort_threshold",
                "qber_sample_fraction",
                "error_correction_efficiency",
                "reconciliation_block_size",
                "privacy_amplification_enabled",
                "decoy_security_estimation_enabled",
                "decoy_security_method",
            },
        )
        return cls(
            sifting_enabled=data.get("sifting_enabled", True),
            qber_abort_threshold=data.get("qber_abort_threshold", 0.11),
            qber_sample_fraction=data.get("qber_sample_fraction", 0.0),
            error_correction_efficiency=data.get("error_correction_efficiency", 1.0),
            reconciliation_block_size=data.get("reconciliation_block_size", 8),
            privacy_amplification_enabled=data.get(
                "privacy_amplification_enabled",
                False,
            ),
            decoy_security_estimation_enabled=data.get(
                "decoy_security_estimation_enabled",
                True,
            ),
            decoy_security_method=data.get(
                "decoy_security_method",
                "vacuum_weak_asymptotic",
            ),
        )


@dataclass(frozen=True, slots=True)
class EveConfig:
    """Adversarial model configuration for protocol-level attack simulations."""

    kind: str = "none"
    intercept_probability: float = 0.0
    pns_split_probability: float = 1.0
    pns_block_single_photon_probability: float = 0.0

    def __post_init__(self) -> None:
        kind = require_non_empty_str("kind", self.kind).lower()
        if kind == "pns":
            kind = "photon_number_splitting"
        if kind == "no_eve":
            kind = "none"
        if kind not in {
            "none",
            "intercept_resend",
            "photon_number_splitting",
        }:
            raise ValueError(
                "kind must be none, no_eve, intercept_resend, "
                "photon_number_splitting, or pns",
            )
        # "no_eve" and "pns" are accepted aliases normalized above so that
        # equivalent configurations share one canonical serialized form.
        object.__setattr__(self, "kind", kind)
        object.__setattr__(
            self,
            "intercept_probability",
            require_probability(
                "intercept_probability",
                self.intercept_probability,
            ),
        )
        object.__setattr__(
            self,
            "pns_split_probability",
            require_probability(
                "pns_split_probability",
                self.pns_split_probability,
            ),
        )
        object.__setattr__(
            self,
            "pns_block_single_photon_probability",
            require_probability(
                "pns_block_single_photon_probability",
                self.pns_block_single_photon_probability,
            ),
        )

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind,
            "intercept_probability": self.intercept_probability,
            "pns_split_probability": self.pns_split_probability,
            "pns_block_single_photon_probability": (
                self.pns_block_single_photon_probability
            ),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "EveConfig",
            data,
            {
                "kind",
                "intercept_probability",
                "pns_split_probability",
                "pns_block_single_photon_probability",
            },
        )
        return cls(
            kind=data.get("kind", "none"),
            intercept_probability=data.get("intercept_probability", 0.0),
            pns_split_probability=data.get("pns_split_probability", 1.0),
            pns_block_single_photon_probability=data.get(
                "pns_block_single_photon_probability",
                0.0,
            ),
        )


def _normalize_angle_tuple(
    name: str,
    value: tuple[float, ...] | list[float],
) -> tuple[float, ...]:
    if not isinstance(value, tuple | list):
        raise TypeError(f"{name} must be a tuple or list")
    if not value:
        raise ValueError(f"{name} must contain at least one angle")
    return tuple(
        require_finite_number(f"{name}[{index}]", angle)
        for index, angle in enumerate(value)
    )


def _normalize_setting_pairs(
    name: str,
    value: tuple[tuple[int, int], ...] | list[tuple[int, int] | list[int]],
) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, tuple | list):
        raise TypeError(f"{name} must be a tuple or list")
    pairs: list[tuple[int, int]] = []
    for index, pair in enumerate(value):
        if not isinstance(pair, tuple | list) or len(pair) != 2:
            raise TypeError(f"{name}[{index}] must contain two setting indexes")
        alice, bob = pair
        pairs.append(
            (
                require_non_negative_int(f"{name}[{index}][0]", alice),
                require_non_negative_int(f"{name}[{index}][1]", bob),
            ),
        )
    return tuple(pairs)


def _normalize_chsh_terms(
    value: tuple[tuple[int, int, int], ...] | list[tuple[int, int, int] | list[int]],
) -> tuple[tuple[int, int, int], ...]:
    if not isinstance(value, tuple | list):
        raise TypeError("chsh_terms must be a tuple or list")
    terms: list[tuple[int, int, int]] = []
    for index, term in enumerate(value):
        if not isinstance(term, tuple | list) or len(term) != 3:
            raise TypeError("chsh_terms entries must contain three values")
        alice, bob, coefficient = term
        coefficient = int(coefficient)
        if coefficient not in {-1, 1}:
            raise ValueError("chsh term coefficients must be -1 or 1")
        terms.append(
            (
                require_non_negative_int(f"chsh_terms[{index}][0]", alice),
                require_non_negative_int(f"chsh_terms[{index}][1]", bob),
                coefficient,
            ),
        )
    return tuple(terms)


def _require_e91_indexes_in_range(
    *,
    alice_angles_rad: tuple[float, ...],
    bob_angles_rad: tuple[float, ...],
    key_setting_pairs: tuple[tuple[int, int], ...],
    chsh_terms: tuple[tuple[int, int, int], ...],
) -> None:
    for alice, bob in key_setting_pairs:
        if alice >= len(alice_angles_rad):
            raise ValueError("key_setting_pairs references an unknown Alice setting")
        if bob >= len(bob_angles_rad):
            raise ValueError("key_setting_pairs references an unknown Bob setting")
    for alice, bob, _coefficient in chsh_terms:
        if alice >= len(alice_angles_rad):
            raise ValueError("chsh_terms references an unknown Alice setting")
        if bob >= len(bob_angles_rad):
            raise ValueError("chsh_terms references an unknown Bob setting")


@dataclass(frozen=True, slots=True)
class E91Config:
    """Entanglement-based E91 protocol configuration."""

    bell_state: str = "psi_minus"
    alice_angles_rad: tuple[float, ...] = E91_DEFAULT_ALICE_ANGLES_RAD
    bob_angles_rad: tuple[float, ...] = E91_DEFAULT_BOB_ANGLES_RAD
    key_setting_pairs: tuple[tuple[int, int], ...] = E91_DEFAULT_KEY_SETTING_PAIRS
    chsh_terms: tuple[tuple[int, int, int], ...] = E91_DEFAULT_CHSH_TERMS
    bob_key_bit_flip: bool = True
    chsh_estimation_enabled: bool = True

    def __post_init__(self) -> None:
        bell_state = require_non_empty_str("bell_state", self.bell_state).lower()
        object.__setattr__(
            self,
            "bell_state",
            require_choice("bell_state", bell_state, E91_BELL_STATES),
        )
        alice_angles = _normalize_angle_tuple(
            "alice_angles_rad",
            self.alice_angles_rad,
        )
        bob_angles = _normalize_angle_tuple("bob_angles_rad", self.bob_angles_rad)
        key_pairs = _normalize_setting_pairs(
            "key_setting_pairs",
            self.key_setting_pairs,
        )
        chsh_terms = _normalize_chsh_terms(self.chsh_terms)
        _require_e91_indexes_in_range(
            alice_angles_rad=alice_angles,
            bob_angles_rad=bob_angles,
            key_setting_pairs=key_pairs,
            chsh_terms=chsh_terms,
        )
        object.__setattr__(self, "alice_angles_rad", alice_angles)
        object.__setattr__(self, "bob_angles_rad", bob_angles)
        object.__setattr__(self, "key_setting_pairs", key_pairs)
        object.__setattr__(self, "chsh_terms", chsh_terms)
        object.__setattr__(
            self,
            "bob_key_bit_flip",
            require_bool("bob_key_bit_flip", self.bob_key_bit_flip),
        )
        object.__setattr__(
            self,
            "chsh_estimation_enabled",
            require_bool("chsh_estimation_enabled", self.chsh_estimation_enabled),
        )

    def to_dict(self) -> JSONObject:
        return {
            "bell_state": self.bell_state,
            "alice_angles_rad": list(self.alice_angles_rad),
            "bob_angles_rad": list(self.bob_angles_rad),
            "key_setting_pairs": [list(pair) for pair in self.key_setting_pairs],
            "chsh_terms": [list(term) for term in self.chsh_terms],
            "bob_key_bit_flip": self.bob_key_bit_flip,
            "chsh_estimation_enabled": self.chsh_estimation_enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "E91Config",
            data,
            {
                "bell_state",
                "alice_angles_rad",
                "bob_angles_rad",
                "key_setting_pairs",
                "chsh_terms",
                "bob_key_bit_flip",
                "chsh_estimation_enabled",
            },
        )
        return cls(
            bell_state=data.get("bell_state", "psi_minus"),
            alice_angles_rad=tuple(
                data.get("alice_angles_rad", E91_DEFAULT_ALICE_ANGLES_RAD),
            ),
            bob_angles_rad=tuple(
                data.get("bob_angles_rad", E91_DEFAULT_BOB_ANGLES_RAD),
            ),
            key_setting_pairs=tuple(
                data.get("key_setting_pairs", E91_DEFAULT_KEY_SETTING_PAIRS),
            ),
            chsh_terms=tuple(data.get("chsh_terms", E91_DEFAULT_CHSH_TERMS)),
            bob_key_bit_flip=data.get("bob_key_bit_flip", True),
            chsh_estimation_enabled=data.get("chsh_estimation_enabled", True),
        )


@dataclass(frozen=True, slots=True)
class Scenario:
    """Complete reproducible setup for a QKD simulation run."""

    pulses: int
    clock_rate_hz: float
    seed: int
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    post_processing: PostProcessingConfig = field(default_factory=PostProcessingConfig)
    eavesdropper: EveConfig = field(default_factory=EveConfig)
    e91: E91Config = field(default_factory=E91Config)
    dynamic: DynamicConfig = field(default_factory=DynamicConfig)
    event_sample_size: int = 0
    store_full_event_log: bool = False
    metadata: JSONObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pulses", require_positive_int("pulses", self.pulses))
        object.__setattr__(
            self,
            "clock_rate_hz",
            require_positive_number("clock_rate_hz", self.clock_rate_hz),
        )
        object.__setattr__(self, "seed", require_non_negative_int("seed", self.seed))
        object.__setattr__(
            self,
            "event_sample_size",
            require_non_negative_int("event_sample_size", self.event_sample_size),
        )
        object.__setattr__(
            self,
            "store_full_event_log",
            require_bool("store_full_event_log", self.store_full_event_log),
        )
        object.__setattr__(
            self,
            "metadata",
            normalize_metadata("metadata", self.metadata),
        )

    @property
    def duration_s(self) -> float:
        return self.pulses / self.clock_rate_hz

    def to_dict(self) -> JSONObject:
        return {
            "schema_version": SCHEMA_VERSION,
            "pulses": self.pulses,
            "clock_rate_hz": self.clock_rate_hz,
            "seed": self.seed,
            "protocol": self.protocol.to_dict(),
            "source": self.source.to_dict(),
            "channel": self.channel.to_dict(),
            "detector": self.detector.to_dict(),
            "timing": self.timing.to_dict(),
            "post_processing": self.post_processing.to_dict(),
            "eavesdropper": self.eavesdropper.to_dict(),
            "e91": self.e91.to_dict(),
            "dynamic": self.dynamic.to_dict(),
            "event_sample_size": self.event_sample_size,
            "store_full_event_log": self.store_full_event_log,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        allowed = {
            "schema_version",
            "pulses",
            "clock_rate_hz",
            "seed",
            "protocol",
            "source",
            "channel",
            "detector",
            "timing",
            "post_processing",
            "eavesdropper",
            "e91",
            "dynamic",
            "event_sample_size",
            "store_full_event_log",
            "metadata",
        }
        reject_unknown_fields("Scenario", data, allowed)
        schema_version = data.get("schema_version", SCHEMA_VERSION)
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported scenario schema_version: {schema_version}")
        return cls(
            pulses=data["pulses"],
            clock_rate_hz=data["clock_rate_hz"],
            seed=data["seed"],
            protocol=ProtocolConfig.from_dict(data.get("protocol", {})),
            source=SourceConfig.from_dict(data.get("source", {})),
            channel=ChannelConfig.from_dict(data.get("channel", {})),
            detector=DetectorConfig.from_dict(data.get("detector", {})),
            timing=TimingConfig.from_dict(data.get("timing", {})),
            post_processing=PostProcessingConfig.from_dict(
                data.get("post_processing", {}),
            ),
            eavesdropper=EveConfig.from_dict(data.get("eavesdropper", {})),
            e91=E91Config.from_dict(data.get("e91", {})),
            dynamic=DynamicConfig.from_dict(data.get("dynamic", {})),
            event_sample_size=data.get("event_sample_size", 0),
            store_full_event_log=data.get("store_full_event_log", False),
            metadata=data.get("metadata", {}),
        )

    def to_json(self) -> str:
        return dumps_pretty(self.to_dict())

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(loads_object(payload))

    def digest(self) -> str:
        encoded = dumps_canonical(self.to_dict()).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def reproducibility_summary(self, sample_size: int = 5) -> JSONObject:
        return {
            "scenario_digest": self.digest(),
            "seed": self.seed,
            "rng": "python.random.Random",
            "unit_interval_sample": list(sample_unit_interval(self.seed, sample_size)),
        }
