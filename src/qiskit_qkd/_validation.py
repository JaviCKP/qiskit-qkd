"""Validation helpers for public dataclasses."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ._json import JSONObject, normalize_json_object


def require_bool(name: str, value: bool) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean")
    return value


def require_non_empty_str(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def require_positive_int(name: str, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return value


def require_non_negative_int(name: str, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return value


def require_finite_number(name: str, value: int | float) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def require_positive_number(name: str, value: int | float) -> float:
    normalized = require_finite_number(name, value)
    if normalized <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return normalized


def require_non_negative_number(name: str, value: int | float) -> float:
    normalized = require_finite_number(name, value)
    if normalized < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return normalized


def require_probability(name: str, value: int | float) -> float:
    normalized = require_finite_number(name, value)
    if not 0 <= normalized <= 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return normalized


def require_optional_probability(name: str, value: int | float | None) -> float | None:
    if value is None:
        return None
    return require_probability(name, value)


def require_minimum_number(name: str, value: int | float, minimum: float) -> float:
    normalized = require_finite_number(name, value)
    if normalized < minimum:
        raise ValueError(f"{name} must be greater than or equal to {minimum}")
    return normalized


def require_choice(name: str, value: str, choices: set[str]) -> str:
    normalized = require_non_empty_str(name, value)
    if normalized not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{name} must be one of: {allowed}")
    return normalized


def normalize_string_tuple(name: str, value: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, tuple | list):
        raise TypeError(f"{name} must be a tuple or list of strings")
    normalized = tuple(
        require_non_empty_str(f"{name}[{index}]", item)
        for index, item in enumerate(value)
    )
    if not normalized:
        raise ValueError(f"{name} must contain at least one value")
    return normalized


def normalize_metadata(name: str, value: Mapping[str, Any]) -> JSONObject:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return normalize_json_object(value, path=name)


def reject_unknown_fields(
    class_name: str,
    data: Mapping[str, Any],
    allowed: set[str],
) -> None:
    unknown = set(data) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"{class_name} received unknown field(s): {names}")
