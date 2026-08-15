"""Time profiles for dynamic simulation parameters."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    reject_unknown_fields,
    require_finite_number,
    require_non_negative_number,
)


def _validate_window(start_s: float, end_s: float) -> tuple[float, float]:
    start = require_non_negative_number("start_s", start_s)
    end = require_non_negative_number("end_s", end_s)
    if end <= start:
        raise ValueError("end_s must be greater than start_s")
    return start, end


def _active_value_time(start_s: float, end_s: float, time_s: float) -> float | None:
    time = require_finite_number("time_s", time_s)
    if start_s <= time <= end_s:
        return time
    return None


@dataclass(frozen=True, slots=True)
class ConstantProfile:
    """Hold a parameter at one value inside a finite time interval."""

    start_s: float
    end_s: float
    value: float

    def __post_init__(self) -> None:
        start, end = _validate_window(self.start_s, self.end_s)
        object.__setattr__(self, "start_s", start)
        object.__setattr__(self, "end_s", end)
        object.__setattr__(self, "value", require_finite_number("value", self.value))

    def value_at(self, time_s: float) -> float | None:
        if _active_value_time(self.start_s, self.end_s, time_s) is None:
            return None
        return self.value

    def to_dict(self) -> JSONObject:
        return {
            "kind": "constant",
            "start_s": self.start_s,
            "end_s": self.end_s,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "ConstantProfile",
            data,
            {"kind", "start_s", "end_s", "value"},
        )
        return cls(
            start_s=data["start_s"],
            end_s=data["end_s"],
            value=data["value"],
        )


@dataclass(frozen=True, slots=True)
class LinearRampProfile:
    """Linearly interpolate a parameter inside a finite time interval."""

    start_s: float
    end_s: float
    start_value: float
    end_value: float

    def __post_init__(self) -> None:
        start, end = _validate_window(self.start_s, self.end_s)
        object.__setattr__(self, "start_s", start)
        object.__setattr__(self, "end_s", end)
        object.__setattr__(
            self,
            "start_value",
            require_finite_number("start_value", self.start_value),
        )
        object.__setattr__(
            self,
            "end_value",
            require_finite_number("end_value", self.end_value),
        )

    def value_at(self, time_s: float) -> float | None:
        time = _active_value_time(self.start_s, self.end_s, time_s)
        if time is None:
            return None
        u = (time - self.start_s) / (self.end_s - self.start_s)
        return self.start_value + (self.end_value - self.start_value) * u

    def to_dict(self) -> JSONObject:
        return {
            "kind": "linear",
            "start_s": self.start_s,
            "end_s": self.end_s,
            "start_value": self.start_value,
            "end_value": self.end_value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "LinearRampProfile",
            data,
            {"kind", "start_s", "end_s", "start_value", "end_value"},
        )
        return cls(
            start_s=data["start_s"],
            end_s=data["end_s"],
            start_value=data["start_value"],
            end_value=data["end_value"],
        )


@dataclass(frozen=True, slots=True)
class ExponentialRampProfile:
    """Exponential-easing interpolation inside a finite time interval.

    The profile uses an exponential easing curve rather than a pure geometric
    interpolation, so it can model ramps that start at zero.
    """

    start_s: float
    end_s: float
    start_value: float
    end_value: float
    curve: float = 4.0

    def __post_init__(self) -> None:
        start, end = _validate_window(self.start_s, self.end_s)
        curve = require_finite_number("curve", self.curve)
        if curve == 0.0:
            raise ValueError("curve must be non-zero")
        object.__setattr__(self, "start_s", start)
        object.__setattr__(self, "end_s", end)
        object.__setattr__(
            self,
            "start_value",
            require_finite_number("start_value", self.start_value),
        )
        object.__setattr__(
            self,
            "end_value",
            require_finite_number("end_value", self.end_value),
        )
        object.__setattr__(self, "curve", curve)

    def value_at(self, time_s: float) -> float | None:
        time = _active_value_time(self.start_s, self.end_s, time_s)
        if time is None:
            return None
        u = (time - self.start_s) / (self.end_s - self.start_s)
        factor = (math.exp(self.curve * u) - 1.0) / (math.exp(self.curve) - 1.0)
        return self.start_value + (self.end_value - self.start_value) * factor

    def to_dict(self) -> JSONObject:
        return {
            "kind": "exponential",
            "start_s": self.start_s,
            "end_s": self.end_s,
            "start_value": self.start_value,
            "end_value": self.end_value,
            "curve": self.curve,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "ExponentialRampProfile",
            data,
            {"kind", "start_s", "end_s", "start_value", "end_value", "curve"},
        )
        return cls(
            start_s=data["start_s"],
            end_s=data["end_s"],
            start_value=data["start_value"],
            end_value=data["end_value"],
            curve=data.get("curve", 4.0),
        )


TimeProfile = ConstantProfile | LinearRampProfile | ExponentialRampProfile


def profile_from_dict(data: Mapping[str, Any]) -> TimeProfile:
    """Build the right profile type from a JSON-safe mapping."""

    kind = data.get("kind")
    if kind == "constant":
        return ConstantProfile.from_dict(data)
    if kind == "linear":
        return LinearRampProfile.from_dict(data)
    if kind == "exponential":
        return ExponentialRampProfile.from_dict(data)
    raise ValueError(f"Unsupported time profile kind: {kind!r}")
