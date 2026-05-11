"""Small JSON helpers shared by configuration and result objects."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, TypeAlias, cast

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


def normalize_json_value(value: Any, *, path: str = "value") -> JSONValue:
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be finite")
        return value
    if isinstance(value, Mapping):
        normalized: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            normalized[key] = normalize_json_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, list | tuple):
        return [
            normalize_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} is not JSON serializable")


def normalize_json_object(
    value: Mapping[str, Any],
    *,
    path: str = "value",
) -> JSONObject:
    normalized = normalize_json_value(value, path=path)
    if not isinstance(normalized, dict):
        raise TypeError(f"{path} must be a JSON object")
    return normalized


def dumps_canonical(value: Mapping[str, Any]) -> str:
    normalized = normalize_json_object(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def dumps_pretty(value: Mapping[str, Any]) -> str:
    normalized = normalize_json_object(value)
    return json.dumps(normalized, indent=2, sort_keys=True)


def loads_object(payload: str) -> JSONObject:
    loaded = json.loads(payload)
    if not isinstance(loaded, dict):
        raise ValueError("JSON payload must contain an object")
    return cast(JSONObject, normalize_json_object(loaded))
