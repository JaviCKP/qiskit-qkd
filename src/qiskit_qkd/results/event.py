"""Event records for sampled QKD simulation rounds."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    normalize_metadata,
    reject_unknown_fields,
    require_bool,
    require_choice,
    require_non_empty_str,
    require_non_negative_int,
    require_non_negative_number,
)

DETECTION_ORIGINS = {"signal", "dark", "background", "none"}


def _validate_bit(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if value not in {0, 1}:
        raise ValueError(f"{name} must be 0, 1, or None")
    return value


def _validate_optional_str(name: str, value: str | None) -> str | None:
    if value is None:
        return None
    return require_non_empty_str(name, value)


@dataclass(frozen=True, slots=True)
class Event:
    """Sampled event with enough fields to trace one protocol round."""

    index: int
    time_s: float
    alice_bit: int | None = None
    alice_basis: str | None = None
    bob_basis: str | None = None
    emitted: bool = False
    photon_number: int = 0
    transmitted: bool = False
    detected: bool = False
    detection_origin: str = "none"
    bob_bit: int | None = None
    sifted: bool = False
    error: bool | None = None
    intensity_class: str | None = None
    party: str | None = None
    phase_slice: int | None = None
    bsm_success: bool | None = None
    detection_pattern: str | None = None
    eve_action: str | None = None
    eve_detectable: bool = False
    tags: JSONObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", require_non_negative_int("index", self.index))
        object.__setattr__(
            self,
            "time_s",
            require_non_negative_number("time_s", self.time_s),
        )
        object.__setattr__(
            self,
            "alice_bit",
            _validate_bit("alice_bit", self.alice_bit),
        )
        object.__setattr__(self, "bob_bit", _validate_bit("bob_bit", self.bob_bit))
        object.__setattr__(
            self,
            "alice_basis",
            _validate_optional_str("alice_basis", self.alice_basis),
        )
        object.__setattr__(
            self,
            "bob_basis",
            _validate_optional_str("bob_basis", self.bob_basis),
        )
        object.__setattr__(self, "emitted", require_bool("emitted", self.emitted))
        object.__setattr__(
            self,
            "photon_number",
            require_non_negative_int("photon_number", self.photon_number),
        )
        object.__setattr__(
            self,
            "transmitted",
            require_bool("transmitted", self.transmitted),
        )
        object.__setattr__(self, "detected", require_bool("detected", self.detected))
        object.__setattr__(
            self,
            "detection_origin",
            require_choice(
                "detection_origin",
                self.detection_origin,
                DETECTION_ORIGINS,
            ),
        )
        object.__setattr__(self, "sifted", require_bool("sifted", self.sifted))
        if self.error is not None:
            object.__setattr__(self, "error", require_bool("error", self.error))
        object.__setattr__(
            self,
            "intensity_class",
            _validate_optional_str("intensity_class", self.intensity_class),
        )
        object.__setattr__(self, "party", _validate_optional_str("party", self.party))
        if self.phase_slice is not None:
            object.__setattr__(
                self,
                "phase_slice",
                require_non_negative_int("phase_slice", self.phase_slice),
            )
        if self.bsm_success is not None:
            object.__setattr__(
                self,
                "bsm_success",
                require_bool("bsm_success", self.bsm_success),
            )
        object.__setattr__(
            self,
            "detection_pattern",
            _validate_optional_str("detection_pattern", self.detection_pattern),
        )
        object.__setattr__(
            self,
            "eve_action",
            _validate_optional_str("eve_action", self.eve_action),
        )
        object.__setattr__(
            self,
            "eve_detectable",
            require_bool("eve_detectable", self.eve_detectable),
        )
        object.__setattr__(self, "tags", normalize_metadata("tags", self.tags))

    def to_dict(self) -> JSONObject:
        return {
            "index": self.index,
            "time_s": self.time_s,
            "alice_bit": self.alice_bit,
            "alice_basis": self.alice_basis,
            "bob_basis": self.bob_basis,
            "emitted": self.emitted,
            "photon_number": self.photon_number,
            "transmitted": self.transmitted,
            "detected": self.detected,
            "detection_origin": self.detection_origin,
            "bob_bit": self.bob_bit,
            "sifted": self.sifted,
            "error": self.error,
            "intensity_class": self.intensity_class,
            "party": self.party,
            "phase_slice": self.phase_slice,
            "bsm_success": self.bsm_success,
            "detection_pattern": self.detection_pattern,
            "eve_action": self.eve_action,
            "eve_detectable": self.eve_detectable,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "Event",
            data,
            {
                "index",
                "time_s",
                "alice_bit",
                "alice_basis",
                "bob_basis",
                "emitted",
                "photon_number",
                "transmitted",
                "detected",
                "detection_origin",
                "bob_bit",
                "sifted",
                "error",
                "intensity_class",
                "party",
                "phase_slice",
                "bsm_success",
                "detection_pattern",
                "eve_action",
                "eve_detectable",
                "tags",
            },
        )
        return cls(
            index=data["index"],
            time_s=data["time_s"],
            alice_bit=data.get("alice_bit"),
            alice_basis=data.get("alice_basis"),
            bob_basis=data.get("bob_basis"),
            emitted=data.get("emitted", False),
            photon_number=data.get("photon_number", 0),
            transmitted=data.get("transmitted", False),
            detected=data.get("detected", False),
            detection_origin=data.get("detection_origin", "none"),
            bob_bit=data.get("bob_bit"),
            sifted=data.get("sifted", False),
            error=data.get("error"),
            intensity_class=data.get("intensity_class"),
            party=data.get("party"),
            phase_slice=data.get("phase_slice"),
            bsm_success=data.get("bsm_success"),
            detection_pattern=data.get("detection_pattern"),
            eve_action=data.get("eve_action"),
            eve_detectable=data.get("eve_detectable", False),
            tags=data.get("tags", {}),
        )
