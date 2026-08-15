"""Versioned contracts shared by the experiment store and HTTP boundary.

The panel deliberately keeps the v1 reader permissive enough for files already
on disk, while v2 writes use explicit object records and a stable envelope.  A
version marker is never treated as permission to reinterpret an old payload;
call :func:`migrate_experiment_v1_to_v2` when an explicit migration is wanted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qiskit_qkd._json import JSONObject, normalize_json_object, normalize_json_value
from qiskit_qkd.config import SCENARIO_SCHEMA_VERSION, migrate_scenario_v1_to_v2

LEGACY_EXPERIMENT_SCHEMA_VERSION = 1
EXPERIMENT_SCHEMA_VERSION = 2
SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS = {
    LEGACY_EXPERIMENT_SCHEMA_VERSION,
    EXPERIMENT_SCHEMA_VERSION,
}


class UnsupportedExperimentVersionError(ValueError):
    """Raised when an experiment document uses an unknown wire version."""

    def __init__(self, found_version: Any) -> None:
        self.found_version = found_version
        self.supported_versions = tuple(sorted(SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS))
        self.suggestion = (
            "Export the experiment as schema_version 2, or upgrade the panel "
            "to a reader that supports the found version."
        )
        super().__init__(
            "Unsupported experiment schema_version "
            f"{found_version!r} (found_version={found_version!r}); "
            f"supported versions are {self.supported_versions}. "
            f"{self.suggestion}"
        )


def require_experiment_schema_version(value: Any) -> int:
    """Validate an experiment version and preserve the found value in errors."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(
            "experiment schema_version must be an integer; "
            f"found_version={value!r}. Use schema_version 1 or 2."
        )
    if value not in SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS:
        raise UnsupportedExperimentVersionError(value)
    return value


def migrate_experiment_v1_to_v2(payload: Mapping[str, Any]) -> JSONObject:
    """Return a validated, additive v2 copy of a historical experiment.

    The source mapping is not modified.  Legacy fields remain present and the
    workspace collections are added when absent; de-duplicating ``last_result``
    is intentionally left to the store because it depends on run records.
    """

    if not isinstance(payload, Mapping):
        raise TypeError(
            "experiment v1 migration requires a mapping, "
            f"got {type(payload).__name__}"
        )
    source_version = payload.get(
        "schema_version",
        LEGACY_EXPERIMENT_SCHEMA_VERSION,
    )
    if source_version != LEGACY_EXPERIMENT_SCHEMA_VERSION:
        if source_version in SUPPORTED_EXPERIMENT_SCHEMA_VERSIONS:
            raise ValueError(
                "experiment migration expects schema_version 1; "
                f"found_version={source_version!r} is already supported"
            )
        raise UnsupportedExperimentVersionError(source_version)
    migrated = normalize_json_object(payload, path="experiment")
    migrated["schema_version"] = EXPERIMENT_SCHEMA_VERSION
    scenario = migrated.get("scenario")
    if (
        isinstance(scenario, Mapping)
        and scenario.get("schema_version", 1) != SCENARIO_SCHEMA_VERSION
    ):
        migrated["scenario"] = migrate_scenario_v1_to_v2(scenario)
    migrated.setdefault("runs", [])
    migrated.setdefault("curves", [])
    migrated.setdefault("provenance", {})
    return migrated


def normalize_record_list(
    value: Any,
    *,
    field: str,
    schema_version: int,
    maximum: int,
) -> list[dict[str, Any]]:
    """Validate workspace records as finite JSON objects, not bare lists."""

    if not isinstance(value, list):
        raise ValueError(f"experiment.{field} must be a list of objects")
    if len(value) > maximum:
        raise ValueError(
            f"experiment.{field} must contain at most {maximum} items; "
            f"got {len(value)}"
        )
    records: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"experiment.{field}[{index}] must be an object; "
                f"got {type(item).__name__}"
            )
        try:
            record = normalize_json_object(item, path=f"experiment.{field}[{index}]")
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        if schema_version >= EXPERIMENT_SCHEMA_VERSION:
            _require_record_identity(record, field=field, index=index)
        records.append(record)
    return records


def normalize_result(
    value: Any,
    *,
    field: str,
    schema_version: int,
) -> dict[str, Any] | None:
    """Validate a result summary and its common nested evidence sections."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(
            f"experiment.{field} must be an object or null; "
            f"got {type(value).__name__}"
        )
    try:
        result = normalize_json_object(value, path=f"experiment.{field}")
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    if schema_version >= EXPERIMENT_SCHEMA_VERSION:
        _validate_result_sections(result, field=field)
    return result


def latest_run_result(runs: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Return the newest embedded run result for legacy API projection."""

    for run in reversed(runs):
        candidate = run.get("result")
        if isinstance(candidate, Mapping):
            return normalize_json_object(candidate, path="experiment.runs.result")
    return None


def _require_record_identity(
    record: Mapping[str, Any],
    *,
    field: str,
    index: int,
) -> None:
    identity_fields = (
        "job_id",
        "jobId",
        "run_id",
        "curve_id",
        "id",
    )
    present = [name for name in identity_fields if name in record]
    if not present:
        raise ValueError(
            f"experiment.{field}[{index}] must include a non-empty job_id, "
            "run_id, curve_id, or id"
        )
    if not any(
        isinstance(record[name], str) and record[name].strip()
        for name in present
    ):
        raise ValueError(
            f"experiment.{field}[{index}] identity must be a non-empty string"
        )


def _validate_result_sections(result: Mapping[str, Any], *, field: str) -> None:
    for section in ("metrics", "provenance", "classical", "qiskit", "decoy", "bell"):
        value = result.get(section)
        if value is not None and not isinstance(value, Mapping):
            raise ValueError(f"experiment.{field}.{section} must be an object")
    event_sample = result.get("event_sample")
    if event_sample is None:
        return
    if not isinstance(event_sample, list):
        raise ValueError(f"experiment.{field}.event_sample must be a list")
    for index, event in enumerate(event_sample):
        if not isinstance(event, Mapping):
            raise ValueError(
                f"experiment.{field}.event_sample[{index}] must be an object"
            )
        normalize_json_value(event, path=f"experiment.{field}.event_sample[{index}]")
