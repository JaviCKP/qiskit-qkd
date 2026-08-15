"""Declarative scientific metadata shared by the panel API and React clients.

This module is intentionally limited to domain facts: scenario defaults,
parameter units/options/applicability, and the scientific part of medium and
preset definitions.  Product copy, colours and icons stay in the web client.
The payload is additive and versioned so older panel clients can continue to
consume the legacy ``sections``/``capabilities`` shape.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from qiskit_qkd._json import JSONObject, normalize_json_value

from .capabilities import parameter_capability_payload
from .schema import (
    BB84_BASIS_CHOICES,
    CHANNEL_KINDS,
    DECOY_SECURITY_METHODS,
    DETECTOR_KINDS,
    E91_BELL_STATES,
    PROTOCOL_NAMES,
    SLOT_ASSIGNMENT_POLICIES,
    SOURCE_KINDS,
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    E91Config,
    EveConfig,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
    TimingConfig,
)

DOMAIN_METADATA_VERSION = 1


# ``Scenario`` requires these three reproducibility inputs.  Keeping one
# instance here means every field default below is read from the validated
# dataclass serializer rather than copied into catalog or TypeScript tables.
DEFAULT_SCENARIO = Scenario(
    pulses=1024,
    clock_rate_hz=1_000_000.0,
    seed=7,
    source=SourceConfig(
        kind="decoy_weak_coherent",
        decoy_intensities=(
            DecoyIntensity("signal", 0.5, 0.8),
            DecoyIntensity("decoy", 0.1, 0.15),
            DecoyIntensity("vacuum", 0.0, 0.05),
        ),
    ),
    channel=ChannelConfig(kind="fiber", distance_km=25.0),
    detector=DetectorConfig(
        kind="threshold",
        efficiency=0.85,
        dark_count_rate_hz=100.0,
    ),
    event_sample_size=200,
)


@dataclass(frozen=True, slots=True)
class DomainField:
    """Scientific display metadata for one flattened scenario field."""

    key: str
    unit: str | None = None
    options: tuple[str, ...] = ()
    visible_when: Mapping[str, object] | None = None

    def to_dict(self, defaults: Mapping[str, object]) -> JSONObject:
        capability = parameter_capability_payload(self.key)
        payload: JSONObject = {
            "key": self.key,
            "default": normalize_json_value(
                defaults.get(self.key),
                path=f"domain_metadata.fields.{self.key}.default",
            ),
            "unit": self.unit,
            "options": list(self.options) or None,
            "visible_when": (
                dict(self.visible_when) if self.visible_when is not None else None
            ),
            **capability,
        }
        if "dependency" in capability:
            payload["dependencies"] = [capability["dependency"]]
        if self.visible_when is not None:
            payload["conditions"] = dict(self.visible_when)
        return payload


def _flatten_defaults(value: Mapping[str, Any]) -> dict[str, object]:
    flattened: dict[str, object] = {}
    for section, section_value in value.items():
        if section in {"schema_version", "metadata"}:
            continue
        if isinstance(section_value, Mapping):
            for field, field_value in section_value.items():
                flattened[f"{section}.{field}"] = field_value
        else:
            flattened[f"scenario.{section}"] = section_value
    return flattened


def _unit_for(key: str) -> str | None:
    explicit = {
        "scenario.clock_rate_hz": "Hz",
        "channel.distance_km": "km",
        "channel.attenuation_db_km": "dB/km",
        "channel.fixed_loss_db": "dB",
        "channel.wavelength_nm": "nm",
        "channel.transmitter_aperture_m": "m",
        "channel.receiver_aperture_m": "m",
        "channel.beam_divergence_rad": "rad",
        "channel.atmospheric_extinction_db_km": "dB/km",
        "channel.underwater_extinction_m_inv": "m⁻¹",
        "channel.underwater_scattering_broadening_ns_per_m": "ns/m",
        "channel.polarization_rotation_y_rad": "rad",
        "channel.polarization_rotation_z_rad": "rad",
        "channel.background_count_rate_hz": "Hz",
        "channel.pmd_coefficient_ps_sqrt_km": "ps/√km",
        "channel.chromatic_dispersion_ps_nm_km": "ps/(nm·km)",
        "channel.source_spectral_width_nm": "nm",
        "channel.polarization_dependent_loss_db": "dB",
        "channel.classical_channel_power_mw": "mW",
        "channel.raman_coefficient_hz_mw_km": "Hz/(mW·km)",
        "channel.raman_filter_isolation_db": "dB",
        "detector.dark_count_rate_hz": "Hz",
        "detector.gate_width_s": "s",
        "detector.dead_time_s": "s",
        "timing.propagation_delay_s": "s",
        "timing.jitter_std_s": "s",
        "timing.clock_offset_s": "s",
        "timing.clock_drift_ppm": "ppm",
    }
    if key in explicit:
        return explicit[key]
    if key.endswith("_bps"):
        return "bit/s"
    if key.endswith("_rate_hz"):
        return "Hz"
    if key.endswith("_rad") or key.endswith("_angles_rad"):
        return "rad"
    if key.endswith("_s"):
        return "s"
    return None


def _options_for(key: str) -> tuple[str, ...]:
    options: dict[str, Iterable[str]] = {
        "protocol.name": sorted(PROTOCOL_NAMES),
        "protocol.basis_choices": sorted(BB84_BASIS_CHOICES),
        "source.kind": sorted(SOURCE_KINDS),
        "channel.kind": sorted(CHANNEL_KINDS),
        "channel.pdl_axis_basis": sorted(BB84_BASIS_CHOICES),
        "detector.kind": sorted(DETECTOR_KINDS),
        "detector.double_click_policy": ("discard", "random", "error"),
        "timing.slot_assignment_policy": sorted(SLOT_ASSIGNMENT_POLICIES),
        "post_processing.decoy_security_method": sorted(DECOY_SECURITY_METHODS),
        "eavesdropper.kind": (
            "none",
            "intercept_resend",
            "photon_number_splitting",
        ),
        "e91.bell_state": sorted(E91_BELL_STATES),
    }
    return tuple(options.get(key, ()))


def _visible_when_for(key: str) -> Mapping[str, object] | None:
    if key.startswith("e91."):
        return {"target": "protocol.name", "equals": "e91"}
    if key == "source.decoy_intensities":
        return {"target": "source.kind", "equals": "decoy_weak_coherent"}
    if key.startswith("eavesdropper.pns_"):
        return {
            "target": "eavesdropper.kind",
            "equals": "photon_number_splitting",
        }
    if key == "eavesdropper.intercept_probability":
        return {"target": "eavesdropper.kind", "equals": "intercept_resend"}
    if key.startswith("post_processing.decoy_"):
        return {"target": "source.kind", "equals": "decoy_weak_coherent"}
    return None


def domain_fields() -> tuple[DomainField, ...]:
    defaults = _flatten_defaults(DEFAULT_SCENARIO.to_dict())
    return tuple(
        DomainField(
            key=key,
            unit=_unit_for(key),
            options=_options_for(key),
            visible_when=_visible_when_for(key),
        )
        for key in sorted(defaults)
    )


def domain_defaults_payload() -> JSONObject:
    defaults = _flatten_defaults(DEFAULT_SCENARIO.to_dict())
    return {
        key: normalize_json_value(value, path=f"domain_metadata.defaults.{key}")
        for key, value in sorted(defaults.items())
    }


def domain_fields_payload() -> list[JSONObject]:
    defaults = domain_defaults_payload()
    return [field.to_dict(defaults) for field in domain_fields()]


def _medium_scenario(
    medium_id: str,
    *,
    source: SourceConfig | None = None,
    channel: ChannelConfig | None = None,
    detector: DetectorConfig | None = None,
    pulses: int | None = None,
) -> Scenario:
    scenario = DEFAULT_SCENARIO
    return replace(
        scenario,
        pulses=scenario.pulses if pulses is None else pulses,
        source=source or scenario.source,
        channel=channel or scenario.channel,
        detector=detector or scenario.detector,
        metadata={"mediumId": medium_id},
    )


def medium_definitions() -> tuple[JSONObject, ...]:
    """Scientific medium definitions; visual presentation is client-owned."""

    decoys = (
        DecoyIntensity("signal", 0.5, 0.8),
        DecoyIntensity("decoy", 0.1, 0.15),
        DecoyIntensity("vacuum", 0.0, 0.05),
    )
    scenarios = (
        (
            "ideal",
            _medium_scenario(
                "ideal",
                source=SourceConfig(kind="ideal_single_photon", decoy_intensities=()),
                channel=ChannelConfig(kind="ideal"),
                detector=DetectorConfig(kind="ideal"),
            ),
            ("ideal",),
        ),
        (
            "fiber",
            _medium_scenario(
                "fiber",
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=decoys,
                ),
                channel=ChannelConfig(
                    kind="fiber",
                    distance_km=100.0,
                    attenuation_db_km=0.2,
                    pmd_coefficient_ps_sqrt_km=0.05,
                    chromatic_dispersion_ps_nm_km=17.0,
                    source_spectral_width_nm=0.1,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.85,
                    dark_count_rate_hz=10.0,
                ),
            ),
            ("fiber",),
        ),
        (
            "vacuum",
            _medium_scenario(
                "vacuum",
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=decoys,
                ),
                channel=ChannelConfig(
                    kind="space",
                    distance_km=1000.0,
                    wavelength_nm=1550.0,
                    transmitter_aperture_m=0.12,
                    receiver_aperture_m=1.2,
                    beam_divergence_rad=2e-6,
                    pointing_jitter_rad=1e-6,
                    background_count_rate_hz=5.0,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.8,
                    dark_count_rate_hz=5.0,
                ),
            ),
            ("space", "deep_space", "vacuum"),
        ),
        (
            "air",
            _medium_scenario(
                "air",
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=decoys,
                ),
                channel=ChannelConfig(
                    kind="free_space",
                    distance_km=1.5,
                    wavelength_nm=850.0,
                    transmitter_aperture_m=0.05,
                    receiver_aperture_m=0.2,
                    beam_divergence_rad=1e-4,
                    atmospheric_extinction_db_km=1.0,
                    scintillation_sigma=0.3,
                    pointing_jitter_rad=5e-6,
                    background_count_rate_hz=500.0,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.65,
                    dark_count_rate_hz=100.0,
                ),
            ),
            ("free_space", "atmospheric"),
        ),
        (
            "satellite",
            _medium_scenario(
                "satellite",
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=decoys,
                ),
                channel=ChannelConfig(
                    kind="satellite",
                    distance_km=500.0,
                    fixed_loss_db=2.0,
                    wavelength_nm=850.0,
                    transmitter_aperture_m=0.1,
                    receiver_aperture_m=1.0,
                    beam_divergence_rad=1e-5,
                    atmospheric_extinction_db_km=0.02,
                    scintillation_sigma=0.12,
                    pointing_jitter_rad=2e-6,
                    background_count_rate_hz=250.0,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.7,
                    dark_count_rate_hz=25.0,
                ),
            ),
            ("satellite",),
        ),
        (
            "underwater",
            _medium_scenario(
                "underwater",
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=decoys,
                ),
                channel=ChannelConfig(
                    kind="underwater",
                    distance_km=0.03,
                    wavelength_nm=520.0,
                    transmitter_aperture_m=0.03,
                    receiver_aperture_m=0.08,
                    beam_divergence_rad=1e-3,
                    underwater_extinction_m_inv=0.05,
                    underwater_scattering_broadening_ns_per_m=0.008,
                    background_count_rate_hz=50.0,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.6,
                    dark_count_rate_hz=50.0,
                ),
            ),
            ("underwater", "water", "marine"),
        ),
        ("custom", _medium_scenario("custom"), ()),
    )
    return tuple(
        {
            "id": medium_id,
            "channel_kinds": list(channel_kinds),
            "scenario": scenario.to_dict(),
        }
        for medium_id, scenario, channel_kinds in scenarios
    )


def builtin_presets() -> tuple[tuple[str, Scenario], ...]:
    """Return scientific built-ins used by ``/api/presets``."""

    return (
        (
            "Fibra metropolitana (Ideal)",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=7,
                channel=ChannelConfig(kind="fiber", distance_km=25.0),
            ),
        ),
        (
            "Satélite LEO (Ideal)",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=8,
                channel=ChannelConfig(
                    kind="space",
                    distance_km=500.0,
                    beam_divergence_rad=2e-6,
                ),
            ),
        ),
        (
            "PNS sobre decoy débil",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=9,
                source=SourceConfig(kind="decoy_weak_coherent", decoy_intensities=(
                    DecoyIntensity("signal", 0.5, 0.8),
                    DecoyIntensity("decoy", 0.1, 0.15),
                    DecoyIntensity("vacuum", 0.0, 0.05),
                )),
                eavesdropper=EveConfig(kind="pns", pns_split_probability=0.5),
            ),
        ),
        (
            "E91 con scintillation",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=91,
                protocol=ProtocolConfig(name="e91"),
                source=SourceConfig(kind="entangled_pair"),
                e91=E91Config(),
                channel=ChannelConfig(kind="space", scintillation_sigma=0.2),
                post_processing=PostProcessingConfig(qber_abort_threshold=None),
            ),
        ),
        (
            "Telecom Fibra 100 km (SNSPD Real)",
            Scenario(
                pulses=10000,
                clock_rate_hz=1_000_000_000.0,
                seed=10,
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=(
                        DecoyIntensity("signal", 0.6, 0.50),
                        DecoyIntensity("decoy", 0.2, 0.25),
                        DecoyIntensity("vacuum", 0.0, 0.25),
                    ),
                    preparation_error_probability=0.001,
                ),
                channel=ChannelConfig(
                    kind="fiber",
                    distance_km=100.0,
                    attenuation_db_km=0.2,
                    wavelength_nm=1550.0,
                    chromatic_dispersion_ps_nm_km=17.0,
                    pmd_coefficient_ps_sqrt_km=0.1,
                    source_spectral_width_nm=0.01,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.85,
                    dark_count_rate_hz=10.0,
                    gate_width_s=1e-9,
                    dead_time_s=20e-9,
                    afterpulse_probability=0.001,
                ),
                timing=TimingConfig(jitter_std_s=50e-12),
            ),
        ),
        (
            "Free Space Urbano 1.5 km (SPAD Real)",
            Scenario(
                pulses=10000,
                clock_rate_hz=10_000_000.0,
                seed=11,
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=(
                        DecoyIntensity("signal", 0.6, 0.75),
                        DecoyIntensity("decoy", 0.2, 0.19),
                        DecoyIntensity("vacuum", 0.0, 0.06),
                    ),
                ),
                channel=ChannelConfig(
                    kind="free_space",
                    distance_km=1.5,
                    wavelength_nm=850.0,
                    atmospheric_extinction_db_km=1.0,
                    scintillation_sigma=0.3,
                    pointing_jitter_rad=5e-6,
                    background_count_rate_hz=500.0,
                    transmitter_aperture_m=0.05,
                    receiver_aperture_m=0.15,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.50,
                    dark_count_rate_hz=50.0,
                    gate_width_s=1e-9,
                    dead_time_s=22e-9,
                    afterpulse_probability=0.005,
                ),
                timing=TimingConfig(jitter_std_s=350e-12),
            ),
        ),
        (
            "Enlace Submarino 30 m (Real)",
            Scenario(
                pulses=50000,
                clock_rate_hz=1_000_000.0,
                seed=12,
                source=SourceConfig(kind="weak_coherent", mean_photon_number=0.5),
                channel=ChannelConfig(
                    kind="underwater",
                    distance_km=0.030,
                    wavelength_nm=520.0,
                    underwater_extinction_m_inv=0.05,
                    underwater_scattering_broadening_ns_per_m=0.008,
                    background_count_rate_hz=200.0,
                    transmitter_aperture_m=0.03,
                    receiver_aperture_m=0.10,
                ),
                detector=DetectorConfig(
                    kind="threshold",
                    efficiency=0.50,
                    dark_count_rate_hz=200.0,
                    gate_width_s=1e-9,
                    dead_time_s=50e-9,
                    afterpulse_probability=0.01,
                ),
            ),
        ),
    )


def domain_metadata_payload() -> JSONObject:
    return {
        "metadata_version": DOMAIN_METADATA_VERSION,
        "default_medium_id": "fiber",
        "default_scenario": DEFAULT_SCENARIO.to_dict(),
        "field_defaults": domain_defaults_payload(),
        "fields": domain_fields_payload(),
        "media": list(medium_definitions()),
    }
