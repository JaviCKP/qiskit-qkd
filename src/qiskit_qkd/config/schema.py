"""Validated configuration objects for reproducible QKD scenarios."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from qiskit_qkd._json import JSONObject, dumps_canonical, dumps_pretty, loads_object
from qiskit_qkd._validation import (
    normalize_metadata,
    normalize_string_tuple,
    reject_unknown_fields,
    require_bool,
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

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProtocolConfig:
    """Protocol-level configuration for a QKD scenario."""

    name: str = "bb84"
    basis_choices: tuple[str, ...] = ("Z", "X")

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_non_empty_str("name", self.name))
        object.__setattr__(
            self,
            "basis_choices",
            normalize_string_tuple("basis_choices", self.basis_choices),
        )

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
class SourceConfig:
    """Source configuration with explicit emission probabilities."""

    kind: str = "ideal_single_photon"
    emission_probability: float = 1.0
    mean_photon_number: float | None = None
    preparation_error_probability: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", require_non_empty_str("kind", self.kind))
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

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind,
            "emission_probability": self.emission_probability,
            "mean_photon_number": self.mean_photon_number,
            "preparation_error_probability": self.preparation_error_probability,
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
        )


@dataclass(frozen=True, slots=True)
class ChannelConfig:
    """Physical channel parameters with distance and loss units in field names."""

    kind: str = "ideal"
    distance_km: float = 0.0
    attenuation_db_km: float = 0.0
    fixed_loss_db: float = 0.0
    depolarizing_probability: float = 0.0
    phase_damping_probability: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", require_non_empty_str("kind", self.kind))
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

    def to_dict(self) -> JSONObject:
        return {
            "kind": self.kind,
            "distance_km": self.distance_km,
            "attenuation_db_km": self.attenuation_db_km,
            "fixed_loss_db": self.fixed_loss_db,
            "depolarizing_probability": self.depolarizing_probability,
            "phase_damping_probability": self.phase_damping_probability,
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
                "depolarizing_probability",
                "phase_damping_probability",
            },
        )
        return cls(
            kind=data.get("kind", "ideal"),
            distance_km=data.get("distance_km", 0.0),
            attenuation_db_km=data.get("attenuation_db_km", 0.0),
            fixed_loss_db=data.get("fixed_loss_db", 0.0),
            depolarizing_probability=data.get("depolarizing_probability", 0.0),
            phase_damping_probability=data.get("phase_damping_probability", 0.0),
        )


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Detector configuration with timing, efficiency, and readout parameters."""

    kind: str = "ideal"
    efficiency: float = 1.0
    dark_count_rate_hz: float = 0.0
    gate_width_s: float = 1e-9
    readout_error_probability: float = 0.0
    double_click_policy: str = "discard"

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", require_non_empty_str("kind", self.kind))
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
                "readout_error_probability",
                "double_click_policy",
            },
        )
        return cls(
            kind=data.get("kind", "ideal"),
            efficiency=data.get("efficiency", 1.0),
            dark_count_rate_hz=data.get("dark_count_rate_hz", 0.0),
            gate_width_s=data.get("gate_width_s", 1e-9),
            readout_error_probability=data.get("readout_error_probability", 0.0),
            double_click_policy=data.get("double_click_policy", "discard"),
        )


@dataclass(frozen=True, slots=True)
class PostProcessingConfig:
    """Classical post-processing parameters used after measurement."""

    sifting_enabled: bool = True
    qber_abort_threshold: float | None = 0.11
    error_correction_efficiency: float = 1.0
    privacy_amplification_enabled: bool = False

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
            "error_correction_efficiency",
            require_minimum_number(
                "error_correction_efficiency",
                self.error_correction_efficiency,
                1.0,
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

    def to_dict(self) -> JSONObject:
        return {
            "sifting_enabled": self.sifting_enabled,
            "qber_abort_threshold": self.qber_abort_threshold,
            "error_correction_efficiency": self.error_correction_efficiency,
            "privacy_amplification_enabled": self.privacy_amplification_enabled,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "PostProcessingConfig",
            data,
            {
                "sifting_enabled",
                "qber_abort_threshold",
                "error_correction_efficiency",
                "privacy_amplification_enabled",
            },
        )
        return cls(
            sifting_enabled=data.get("sifting_enabled", True),
            qber_abort_threshold=data.get("qber_abort_threshold", 0.11),
            error_correction_efficiency=data.get("error_correction_efficiency", 1.0),
            privacy_amplification_enabled=data.get(
                "privacy_amplification_enabled",
                False,
            ),
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
    post_processing: PostProcessingConfig = field(default_factory=PostProcessingConfig)
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
            "post_processing": self.post_processing.to_dict(),
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
            "post_processing",
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
            post_processing=PostProcessingConfig.from_dict(
                data.get("post_processing", {}),
            ),
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
