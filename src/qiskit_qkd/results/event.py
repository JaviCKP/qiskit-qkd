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
    require_finite_number,
    require_non_empty_str,
    require_non_negative_int,
    require_non_negative_number,
)

DETECTION_ORIGINS = {"signal", "dark", "background", "afterpulse", "none"}
TIMING_STATUSES = {
    "not_evaluated",
    "no_signal",
    "in_gate",
    "early",
    "late",
    "assigned_nearest",
    "ambiguous",
    "dead_time",
}


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


def _validate_optional_slot(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    return require_non_negative_int(name, value)


def _validate_optional_time(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    return require_finite_number(name, value)


@dataclass(frozen=True, slots=True)
class Event:
    """Sampled event with enough fields to trace one protocol round."""

    index: int
    time_s: float
    time_slot: int | None = None

    # Timing metadata. `index` is retained for compatibility; `time_slot` names
    # the shared Alice/Bob clock window represented by this event.
    emission_time_s: float | None = None
    expected_arrival_time_s: float | None = None
    arrival_time_s: float | None = None
    bob_gate_start_s: float | None = None
    bob_gate_end_s: float | None = None
    assigned_slot: int | None = None
    timing_status: str = "not_evaluated"

    # Preparation choices for prepare-and-measure protocols such as BB84.
    alice_bit: int | None = None
    alice_basis: str | None = None
    bob_basis: str | None = None

    # Source and channel outcomes.
    emitted: bool = False
    photon_number: int = 0
    intensity_class: str | None = None
    transmitted: bool = False

    # Receiver and measurement outcomes.
    detected: bool = False
    detection_origin: str = "none"
    bob_bit: int | None = None
    detection_pattern: str | None = None

    # Classical post-processing outcomes.
    sifted: bool = False
    error: bool | None = None

    # Extension fields for multi-party, phase-encoded, and BSM-based protocols.
    party: str | None = None
    phase_slice: int | None = None
    bsm_success: bool | None = None

    # Explicit adversarial action, kept separate from accidental noise.
    eve_action: str | None = None
    eve_basis: str | None = None
    eve_detectable: bool = False
    tags: JSONObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "index", require_non_negative_int("index", self.index))
        object.__setattr__(
            self,
            "time_s",
            require_non_negative_number("time_s", self.time_s),
        )
        time_slot = self.index if self.time_slot is None else self.time_slot
        object.__setattr__(
            self,
            "time_slot",
            require_non_negative_int("time_slot", time_slot),
        )
        emission_time_s = (
            self.time_s if self.emission_time_s is None else self.emission_time_s
        )
        object.__setattr__(
            self,
            "emission_time_s",
            _validate_optional_time("emission_time_s", emission_time_s),
        )
        object.__setattr__(
            self,
            "expected_arrival_time_s",
            _validate_optional_time(
                "expected_arrival_time_s",
                self.expected_arrival_time_s,
            ),
        )
        object.__setattr__(
            self,
            "arrival_time_s",
            _validate_optional_time("arrival_time_s", self.arrival_time_s),
        )
        object.__setattr__(
            self,
            "bob_gate_start_s",
            _validate_optional_time("bob_gate_start_s", self.bob_gate_start_s),
        )
        object.__setattr__(
            self,
            "bob_gate_end_s",
            _validate_optional_time("bob_gate_end_s", self.bob_gate_end_s),
        )
        if (
            self.bob_gate_start_s is not None
            and self.bob_gate_end_s is not None
            and self.bob_gate_end_s < self.bob_gate_start_s
        ):
            raise ValueError("bob_gate_end_s must be greater than bob_gate_start_s")
        object.__setattr__(
            self,
            "assigned_slot",
            _validate_optional_slot("assigned_slot", self.assigned_slot),
        )
        object.__setattr__(
            self,
            "timing_status",
            require_choice("timing_status", self.timing_status, TIMING_STATUSES),
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
            "eve_basis",
            _validate_optional_str("eve_basis", self.eve_basis),
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
            "time_slot": self.time_slot,
            "time_s": self.time_s,
            "emission_time_s": self.emission_time_s,
            "expected_arrival_time_s": self.expected_arrival_time_s,
            "arrival_time_s": self.arrival_time_s,
            "bob_gate_start_s": self.bob_gate_start_s,
            "bob_gate_end_s": self.bob_gate_end_s,
            "assigned_slot": self.assigned_slot,
            "timing_status": self.timing_status,
            "alice_bit": self.alice_bit,
            "alice_basis": self.alice_basis,
            "bob_basis": self.bob_basis,
            "emitted": self.emitted,
            "photon_number": self.photon_number,
            "intensity_class": self.intensity_class,
            "transmitted": self.transmitted,
            "detected": self.detected,
            "detection_origin": self.detection_origin,
            "bob_bit": self.bob_bit,
            "detection_pattern": self.detection_pattern,
            "sifted": self.sifted,
            "error": self.error,
            "party": self.party,
            "phase_slice": self.phase_slice,
            "bsm_success": self.bsm_success,
            "eve_action": self.eve_action,
            "eve_basis": self.eve_basis,
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
                "time_slot",
                "time_s",
                "emission_time_s",
                "expected_arrival_time_s",
                "arrival_time_s",
                "bob_gate_start_s",
                "bob_gate_end_s",
                "assigned_slot",
                "timing_status",
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
                "eve_basis",
                "eve_detectable",
                "tags",
            },
        )
        return cls(
            index=data["index"],
            time_s=data["time_s"],
            time_slot=data.get("time_slot"),
            emission_time_s=data.get("emission_time_s"),
            expected_arrival_time_s=data.get("expected_arrival_time_s"),
            arrival_time_s=data.get("arrival_time_s"),
            bob_gate_start_s=data.get("bob_gate_start_s"),
            bob_gate_end_s=data.get("bob_gate_end_s"),
            assigned_slot=data.get("assigned_slot"),
            timing_status=data.get("timing_status", "not_evaluated"),
            alice_bit=data.get("alice_bit"),
            alice_basis=data.get("alice_basis"),
            bob_basis=data.get("bob_basis"),
            emitted=data.get("emitted", False),
            photon_number=data.get("photon_number", 0),
            intensity_class=data.get("intensity_class"),
            transmitted=data.get("transmitted", False),
            detected=data.get("detected", False),
            detection_origin=data.get("detection_origin", "none"),
            bob_bit=data.get("bob_bit"),
            detection_pattern=data.get("detection_pattern"),
            sifted=data.get("sifted", False),
            error=data.get("error"),
            party=data.get("party"),
            phase_slice=data.get("phase_slice"),
            bsm_success=data.get("bsm_success"),
            eve_action=data.get("eve_action"),
            eve_basis=data.get("eve_basis"),
            eve_detectable=data.get("eve_detectable", False),
            tags=data.get("tags", {}),
        )
