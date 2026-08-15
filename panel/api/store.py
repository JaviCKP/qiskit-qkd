from __future__ import annotations

import json
import logging
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, BinaryIO

from qiskit_qkd._json import normalize_json_object
from qiskit_qkd.config import (
    Scenario,
    UnsupportedScenarioVersionError,
    require_executable_scenario,
)

from .experiment_contracts import (
    EXPERIMENT_SCHEMA_VERSION,
    LEGACY_EXPERIMENT_SCHEMA_VERSION,
    UnsupportedExperimentVersionError,
    latest_run_result,
    migrate_experiment_v1_to_v2,
    normalize_record_list,
    normalize_result,
    require_experiment_schema_version,
)

logger = logging.getLogger(__name__)

_EXPERIMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class StoreValidationError(ValueError):
    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        message = errors[0].get("msg", "invalid experiment") if errors else "invalid"
        super().__init__(message)


class ExperimentStore:
    def __init__(
        self,
        root: Path,
        *,
        max_payload_bytes: int = 50 * 1024 * 1024,
        max_total_bytes: int = 256 * 1024 * 1024,
        max_tags: int = 64,
        max_curve_recipes: int = 128,
        max_runs: int = 256,
        max_curves: int = 256,
    ) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_payload_bytes = _positive_int(
            "max_payload_bytes",
            max_payload_bytes,
        )
        self.max_total_bytes = _positive_int("max_total_bytes", max_total_bytes)
        if self.max_total_bytes < self.max_payload_bytes:
            raise ValueError(
                "max_total_bytes must be at least max_payload_bytes; "
                f"got {self.max_total_bytes} < {self.max_payload_bytes}"
            )
        self.max_tags = _positive_int("max_tags", max_tags)
        self.max_curve_recipes = _positive_int(
            "max_curve_recipes",
            max_curve_recipes,
        )
        self.max_runs = _positive_int("max_runs", max_runs)
        self.max_curves = _positive_int("max_curves", max_curves)
        self._lock = RLock()

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            experiments = []
            for path in sorted(self.root.glob("*.json")):
                experiment = self._read_or_none(path)
                if experiment is not None:
                    experiments.append(experiment)
            return experiments

    def list_summaries(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List lightweight experiment metadata without result/event payloads.

        ``list()`` remains the historical full-document API.  HTTP callers use
        this method so pagination never returns ``last_result``, runs, curves,
        recipes, or event logs by accident.
        """

        _validate_page(limit, offset)
        with self._lock:
            summaries: list[dict[str, Any]] = []
            valid_count = 0
            for path in sorted(self.root.glob("*.json")):
                summary = self._read_summary_or_none(path)
                if summary is None:
                    continue
                if valid_count >= offset and len(summaries) < limit:
                    summaries.append(summary)
                valid_count += 1
            return summaries, valid_count

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        path = self._path(experiment_id)
        with self._lock:
            if not path.exists():
                return None
            return self._read_or_none(path)

    def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        experiment = self._validate_content(payload)
        experiment_id = experiment.get("id")
        if experiment_id is None:
            experiment_id = f"e_{uuid.uuid4().hex[:12]}"
        experiment_id = self._validate_id(experiment_id)
        path = self._path(experiment_id)

        with self._lock:
            now = datetime.now(UTC)
            created_at = now.isoformat()
            previous_size = 0
            if path.exists():
                existing, previous_size = self._read_strict_with_size(path)
                created_at = str(existing["created_at"])
            experiment["id"] = experiment_id
            experiment["origin"] = "user"
            experiment["created_at"] = created_at
            experiment["updated_at"] = now.isoformat()
            storage_experiment = self._storage_payload(experiment)
            encoded = json.dumps(
                storage_experiment,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            if len(encoded) > self.max_payload_bytes:
                raise _store_error(
                    code="EXPERIMENT_PAYLOAD_LIMIT_EXCEEDED",
                    loc="experiment",
                    msg=(
                        f"Serialized experiment is {len(encoded)} bytes; the limit "
                        f"is {self.max_payload_bytes}."
                    ),
                    value=len(encoded),
                    context={"max_payload_bytes": self.max_payload_bytes},
                    suggestion="Remove large result rows or event data before saving.",
                )
            current_total = self._stored_bytes()
            projected_total = current_total - previous_size + len(encoded)
            if projected_total > self.max_total_bytes:
                raise _store_error(
                    code="EXPERIMENT_TOTAL_QUOTA_EXCEEDED",
                    loc="experiment",
                    msg=(
                        "Experiment store quota would be exceeded: "
                        f"{projected_total} bytes projected, limit is "
                        f"{self.max_total_bytes}."
                    ),
                    value=projected_total,
                    context={
                        "stored_bytes": current_total,
                        "replaced_bytes": previous_size,
                        "payload_bytes": len(encoded),
                        "max_total_bytes": self.max_total_bytes,
                    },
                    suggestion=(
                        "Delete an experiment explicitly or remove result/event "
                        "data before saving."
                    ),
                )
            self._atomic_write(path, encoded)
            return self._public_payload(experiment)

    @staticmethod
    def migrate_v1_to_v2(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Expose the explicit, non-writing v1-to-v2 migration boundary."""

        return migrate_experiment_v1_to_v2(payload)

    def delete(self, experiment_id: str) -> bool:
        path = self._path(experiment_id)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            return True

    def _path(self, experiment_id: str) -> Path:
        safe_id = self._validate_id(experiment_id)
        path = self.root / f"{safe_id}.json"
        if path.parent != self.root:  # pragma: no cover - allowlist is primary guard
            raise _invalid_id(experiment_id)
        return path

    def _storage_payload(self, experiment: Mapping[str, Any]) -> dict[str, Any]:
        """Drop only a duplicated v2 last_result before writing to disk."""

        payload = dict(experiment)
        if payload.get("schema_version") != EXPERIMENT_SCHEMA_VERSION:
            return payload
        runs = payload.get("runs")
        result = payload.get("last_result")
        if isinstance(runs, list) and isinstance(result, Mapping):
            latest = latest_run_result(
                [item for item in runs if isinstance(item, Mapping)],
            )
            if latest is not None and dict(latest) == dict(result):
                payload.pop("last_result", None)
        return payload

    def _public_payload(self, experiment: Mapping[str, Any]) -> dict[str, Any]:
        """Project the historical top-level result for API compatibility."""

        payload = dict(experiment)
        if payload.get("last_result") is None:
            runs = payload.get("runs")
            if isinstance(runs, list):
                latest = latest_run_result(
                    [item for item in runs if isinstance(item, Mapping)],
                )
                if latest is not None:
                    payload["last_result"] = latest
        return payload

    def _stored_bytes(self) -> int:
        total = 0
        for path in self.root.glob("*.json"):
            try:
                total += self._contained_file_size(path)
            except (OSError, ValueError):
                logger.warning(
                    "Skipping unsafe experiment path %s while measuring quota",
                    path.name,
                    exc_info=True,
                )
        return total

    def _validate_content(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise _store_error(
                code="EXPERIMENT_OBJECT_REQUIRED",
                loc="experiment",
                msg="experiment must be a JSON object",
                value=type(payload).__name__,
                context={},
                suggestion="Import an exported experiment JSON object.",
            )
        try:
            experiment = normalize_json_object(payload, path="experiment")
        except (RecursionError, TypeError, ValueError) as exc:
            raise _store_error(
                code="EXPERIMENT_JSON_INVALID",
                loc="experiment",
                msg=(
                    "experiment must contain only finite JSON values: "
                    f"{exc}"
                ),
                value=None,
                context={},
                suggestion="Remove non-finite numbers and non-JSON values.",
            ) from exc

        if "id" in experiment:
            self._validate_id(experiment["id"])
        name = experiment.get("name", "Experimento sin titulo")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise _store_error(
                code="EXPERIMENT_NAME_INVALID",
                loc="experiment.name",
                msg="experiment.name must be a non-empty string of at most 200 chars",
                value=name,
                context={"max_characters": 200},
                suggestion="Provide a shorter non-empty experiment name.",
            )
        experiment["name"] = name.strip()

        schema_version = experiment.get(
            "schema_version",
            LEGACY_EXPERIMENT_SCHEMA_VERSION,
        )
        try:
            schema_version = require_experiment_schema_version(schema_version)
        except UnsupportedExperimentVersionError as exc:
            raise _store_error(
                code="EXPERIMENT_SCHEMA_VERSION_UNSUPPORTED",
                loc="experiment.schema_version",
                msg=str(exc),
                value=exc.found_version,
                context={
                    "found_version": exc.found_version,
                    "supported_versions": list(exc.supported_versions),
                },
                suggestion=exc.suggestion,
            ) from exc
        except ValueError as exc:
            raise _store_error(
                code="EXPERIMENT_SCHEMA_VERSION_INVALID",
                loc="experiment.schema_version",
                msg=str(exc),
                value=schema_version,
                context={"found_version": schema_version},
                suggestion="Use schema_version 1 or 2 for experiment exports.",
            ) from exc
        experiment["schema_version"] = schema_version
        if schema_version >= EXPERIMENT_SCHEMA_VERSION:
            allowed_fields = {
                "id",
                "origin",
                "name",
                "schema_version",
                "digest",
                "scenario",
                "tags",
                "last_result",
                "curve_recipes",
                "runs",
                "curves",
                "provenance",
                "created_at",
                "updated_at",
            }
            unknown_fields = sorted(set(experiment) - allowed_fields)
            if unknown_fields:
                raise _store_error(
                    code="EXPERIMENT_UNKNOWN_FIELD",
                    loc="experiment",
                    msg=(
                        "experiment contains unsupported v2 field(s): "
                        + ", ".join(unknown_fields)
                    ),
                    value=unknown_fields,
                    context={"allowed_fields": sorted(allowed_fields)},
                    suggestion=(
                        "Remove unknown fields or migrate the document explicitly."
                    ),
                )

        scenario_payload = experiment.get("scenario")
        if not isinstance(scenario_payload, Mapping):
            raise _store_error(
                code="EXPERIMENT_SCENARIO_REQUIRED",
                loc="experiment.scenario",
                msg="experiment.scenario must be a complete scenario object",
                value=scenario_payload,
                context={},
                suggestion="Include the scenario from an exported experiment.",
            )
        try:
            scenario = Scenario.from_dict(scenario_payload)
            require_executable_scenario(scenario)
        except UnsupportedScenarioVersionError as exc:
            raise _store_error(
                code="EXPERIMENT_SCENARIO_SCHEMA_VERSION_UNSUPPORTED",
                loc="experiment.scenario.schema_version",
                msg=str(exc),
                value=exc.found_version,
                context={
                    "found_version": exc.found_version,
                    "supported_versions": list(exc.supported_versions),
                },
                suggestion=exc.suggestion,
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise _store_error(
                code="EXPERIMENT_SCENARIO_INVALID",
                loc="experiment.scenario",
                msg=f"experiment.scenario is invalid: {exc}",
                value=None,
                context={},
                suggestion="Validate the scenario before importing it.",
            ) from exc
        canonical_digest = scenario.digest()
        supplied_digest = experiment.get("digest")
        if supplied_digest is not None and supplied_digest != canonical_digest:
            raise _store_error(
                code="EXPERIMENT_DIGEST_MISMATCH",
                loc="experiment.digest",
                msg="experiment.digest does not match experiment.scenario",
                value=supplied_digest,
                context={"expected_digest": canonical_digest},
                suggestion="Re-export the experiment or remove the stale digest.",
            )
        scenario_wire_version = (
            2 if schema_version >= EXPERIMENT_SCHEMA_VERSION else None
        )
        experiment["scenario"] = scenario.to_dict(scenario_wire_version)
        experiment["digest"] = canonical_digest
        experiment["tags"] = self._validate_string_list(
            experiment.get("tags", []),
            field="tags",
            maximum=self.max_tags,
        )
        recipes = experiment.get("curve_recipes", [])
        if not isinstance(recipes, list):
            raise _store_error(
                code="EXPERIMENT_CURVE_RECIPES_INVALID",
                loc="experiment.curve_recipes",
                msg="experiment.curve_recipes must be a list",
                value=type(recipes).__name__,
                context={},
                suggestion="Use a JSON array for curve_recipes.",
            )
        if len(recipes) > self.max_curve_recipes:
            raise _store_error(
                code="EXPERIMENT_CURVE_RECIPE_LIMIT_EXCEEDED",
                loc="experiment.curve_recipes",
                msg=(
                    "experiment.curve_recipes must contain at most "
                    f"{self.max_curve_recipes} items"
                ),
                value=len(recipes),
                context={"max_curve_recipes": self.max_curve_recipes},
                suggestion="Remove unused curve recipes before saving.",
            )
        if schema_version >= EXPERIMENT_SCHEMA_VERSION and not all(
            isinstance(item, Mapping) for item in recipes
        ):
            invalid_recipe = next(
                (item for item in recipes if not isinstance(item, Mapping)),
                None,
            )
            raise _store_error(
                code="EXPERIMENT_CURVE_RECIPES_INVALID",
                loc="experiment.curve_recipes",
                msg="experiment.curve_recipes items must be objects in v2",
                value=type(invalid_recipe).__name__,
                context={"schema_version": schema_version},
                suggestion="Use an object containing the curve axis and metric.",
            )
        experiment["curve_recipes"] = [
            dict(item) if isinstance(item, Mapping) else item for item in recipes
        ]
        try:
            experiment["last_result"] = normalize_result(
                experiment.get("last_result"),
                field="last_result",
                schema_version=schema_version,
            )
        except ValueError as exc:
            raise _store_error(
                code="EXPERIMENT_RESULT_INVALID",
                loc="experiment.last_result",
                msg=str(exc),
                value=None,
                context={"schema_version": schema_version},
                suggestion="Store a finite result summary object or null.",
            ) from exc
        try:
            experiment["runs"] = normalize_record_list(
                experiment.get("runs", []),
                field="runs",
                schema_version=schema_version,
                maximum=self.max_runs,
            )
            experiment["curves"] = normalize_record_list(
                experiment.get("curves", []),
                field="curves",
                schema_version=schema_version,
                maximum=self.max_curves,
            )
        except ValueError as exc:
            field_name = "runs" if "runs" in str(exc) else "curves"
            raise _store_error(
                code=f"EXPERIMENT_{field_name.upper()}_INVALID",
                loc=f"experiment.{field_name}",
                msg=str(exc),
                value=None,
                context={"schema_version": schema_version},
                suggestion=(
                    f"Store {field_name} as finite JSON objects with a stable id."
                ),
            ) from exc
        provenance = experiment.get("provenance", {})
        if not isinstance(provenance, Mapping):
            raise _store_error(
                code="EXPERIMENT_PROVENANCE_INVALID",
                loc="experiment.provenance",
                msg="experiment.provenance must be an object",
                value=type(provenance).__name__,
                context={},
                suggestion="Use a JSON object for provenance.",
            )
        experiment["provenance"] = dict(provenance)
        return experiment

    def _validate_object_list(
        self,
        value: Any,
        *,
        field: str,
        maximum: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not all(
            isinstance(item, Mapping) for item in value
        ):
            raise _store_error(
                code=f"EXPERIMENT_{field.upper()}_INVALID",
                loc=f"experiment.{field}",
                msg=f"experiment.{field} must be a list of objects",
                value=type(value).__name__,
                context={},
                suggestion=f"Use a JSON array of objects for {field}.",
            )
        if len(value) > maximum:
            raise _store_error(
                code=f"EXPERIMENT_{field.upper()}_LIMIT_EXCEEDED",
                loc=f"experiment.{field}",
                msg=f"experiment.{field} must contain at most {maximum} items",
                value=len(value),
                context={f"max_{field}": maximum},
                suggestion=f"Remove old {field} before saving.",
            )
        return [dict(item) for item in value]

    def _validate_string_list(
        self,
        value: Any,
        *,
        field: str,
        maximum: int,
    ) -> list[str]:
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise _store_error(
                code="EXPERIMENT_TAGS_INVALID",
                loc=f"experiment.{field}",
                msg=f"experiment.{field} must be a list of non-empty strings",
                value=value,
                context={},
                suggestion=f"Use a JSON array of labels for {field}.",
            )
        if len(value) > maximum:
            raise _store_error(
                code="EXPERIMENT_TAG_LIMIT_EXCEEDED",
                loc=f"experiment.{field}",
                msg=f"experiment.{field} must contain at most {maximum} items",
                value=len(value),
                context={f"max_{field}": maximum},
                suggestion=f"Reduce {field} to at most {maximum} items.",
            )
        return [item.strip() for item in value]

    def _validate_id(self, value: Any) -> str:
        if not isinstance(value, str) or _EXPERIMENT_ID.fullmatch(value) is None:
            raise _invalid_id(value)
        return value

    def _read_or_none(self, path: Path) -> dict[str, Any] | None:
        try:
            return self._read_strict(path)
        except (
            OSError,
            RecursionError,
            json.JSONDecodeError,
            StoreValidationError,
            ValueError,
        ):
            logger.warning(
                "Skipping corrupt experiment file %s",
                path.name,
                exc_info=True,
            )
            return None

    def _read_strict(self, path: Path) -> dict[str, Any]:
        experiment, _ = self._read_strict_with_size(path)
        return experiment

    def _read_strict_with_size(
        self,
        path: Path,
    ) -> tuple[dict[str, Any], int]:
        encoded, size = self._read_contained_bytes(path)
        raw = json.loads(encoded.decode("utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("stored experiment must be a JSON object")
        experiment = self._validate_content(raw)
        expected_id = path.stem
        if experiment.get("id") != expected_id:
            raise ValueError(
                f"stored experiment id does not match filename {expected_id!r}",
            )
        created_at = _parse_timestamp(experiment.get("created_at"), "created_at")
        updated_at = _parse_timestamp(experiment.get("updated_at"), "updated_at")
        if updated_at < created_at:
            raise ValueError("updated_at must not precede created_at")
        experiment["origin"] = "user"
        return self._public_payload(experiment), size

    def _read_summary_or_none(self, path: Path) -> dict[str, Any] | None:
        try:
            encoded, _ = self._read_contained_bytes(path)
            raw = json.loads(encoded.decode("utf-8"))
            if not isinstance(raw, Mapping):
                raise ValueError("stored experiment must be a JSON object")
            experiment_id = raw.get("id")
            if experiment_id != path.stem:
                raise ValueError(
                    f"stored experiment id does not match filename {path.stem!r}"
                )
            version = require_experiment_schema_version(
                raw.get("schema_version", LEGACY_EXPERIMENT_SCHEMA_VERSION),
            )
            name = raw.get("name", "Experimento sin titulo")
            digest = raw.get("digest")
            scenario_payload = raw.get("scenario")
            tags = raw.get("tags", [])
            created_at = _parse_timestamp(raw.get("created_at"), "created_at")
            updated_at = _parse_timestamp(raw.get("updated_at"), "updated_at")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name must be a non-empty string")
            if not isinstance(digest, str) or not digest:
                raise ValueError("digest must be a non-empty string")
            if not isinstance(scenario_payload, Mapping):
                raise ValueError("scenario must be an object")
            scenario = Scenario.from_dict(scenario_payload)
            if scenario.digest() != digest:
                raise ValueError("digest does not match scenario")
            if not isinstance(tags, list) or not all(
                isinstance(tag, str) and tag.strip() for tag in tags
            ):
                raise ValueError("tags must be a list of non-empty strings")
            if updated_at < created_at:
                raise ValueError("updated_at must not precede created_at")
            runs = raw.get("runs", [])
            curves = raw.get("curves", [])
            if not isinstance(runs, list):
                raise ValueError("runs must be a list")
            if not isinstance(curves, list):
                raise ValueError("curves must be a list")
            return {
                "id": experiment_id,
                "origin": "user",
                "name": name.strip(),
                "schema_version": version,
                "digest": digest,
                "tags": [tag.strip() for tag in tags],
                "created_at": created_at.isoformat(),
                "updated_at": updated_at.isoformat(),
                "runs_count": len(runs),
                "curves_count": len(curves),
            }
        except (
            OSError,
            RecursionError,
            json.JSONDecodeError,
            StoreValidationError,
            ValueError,
        ):
            logger.warning(
                "Skipping corrupt experiment file %s while listing summaries",
                path.name,
                exc_info=True,
            )
            return None

    def _atomic_write(self, path: Path, encoded: bytes) -> None:
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root,
            prefix=f".{path.stem}.",
            suffix=".tmp",
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
            _fsync_directory(self.root)
        finally:
            temp_path.unlink(missing_ok=True)

    def _read_contained_bytes(self, path: Path) -> tuple[bytes, int]:
        with self._open_contained_file(path) as (stream, size):
            return stream.read(), size

    def _contained_file_size(self, path: Path) -> int:
        with self._open_contained_file(path) as (_, size):
            return size

    @contextmanager
    def _open_contained_file(
        self,
        path: Path,
    ) -> Iterator[tuple[BinaryIO, int]]:
        """Open and validate one direct store child through the same descriptor."""

        if path.parent != self.root:
            raise ValueError(
                f"experiment path {path.name!r} escaped the configured store"
            )
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        stream: BinaryIO | None = None
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise ValueError(
                    f"experiment path {path.name!r} must be a regular file"
                )
            _verify_opened_path(
                descriptor=descriptor,
                path=path,
                root=self.root,
                opened=opened,
            )
            stream = os.fdopen(descriptor, "rb", closefd=True)
            descriptor = -1
            yield stream, int(opened.st_size)
        finally:
            if stream is not None:
                stream.close()
            elif descriptor >= 0:
                os.close(descriptor)


def _verify_opened_path(
    *,
    descriptor: int,
    path: Path,
    root: Path,
    opened: os.stat_result,
) -> None:
    """Fail closed if an opened file is a link, escape, or raced replacement."""

    resolved = (
        _windows_final_path(descriptor)
        if os.name == "nt"
        else path.resolve(strict=True)
    )
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"experiment path {path.name!r} escaped the configured store"
        ) from exc
    if resolved.parent != root or resolved.name != path.name:
        raise ValueError(
            f"experiment path {path.name!r} must be a direct regular file"
        )

    current = os.lstat(path)
    if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
        raise ValueError(f"experiment path {path.name!r} must not be a link")
    if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
        raise ValueError(
            f"experiment path {path.name!r} changed while it was being opened"
        )


def _windows_final_path(descriptor: int) -> Path:
    """Resolve the file behind an open Windows descriptor without a path race."""

    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_final_path = kernel32.GetFinalPathNameByHandleW
    get_final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_final_path.restype = wintypes.DWORD
    handle = msvcrt.get_osfhandle(descriptor)
    required = get_final_path(handle, None, 0, 0)
    if required == 0:
        error = ctypes.get_last_error()
        raise OSError(error, "could not resolve opened experiment file")
    buffer = ctypes.create_unicode_buffer(required + 1)
    written = get_final_path(handle, buffer, len(buffer), 0)
    if written == 0 or written >= len(buffer):
        error = ctypes.get_last_error()
        raise OSError(error, "could not resolve opened experiment file")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = f"\\\\{value[8:]}"
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return Path(value).resolve(strict=True)


def _fsync_directory(directory: Path) -> None:
    """Durably commit a rename where the platform exposes directory fsync."""

    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        # Windows does not expose a portable directory handle through os.open.
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _invalid_id(value: Any) -> StoreValidationError:
    return _store_error(
        code="EXPERIMENT_ID_INVALID",
        loc="experiment.id",
        msg=(
            "experiment identifier must use 1-64 ASCII letters, digits, "
            "underscores, or hyphens and cannot start with punctuation"
        ),
        value=value,
        context={"pattern": _EXPERIMENT_ID.pattern},
        suggestion="Use an identifier such as 'e_0123abcd'.",
    )


def _store_error(
    *,
    code: str,
    loc: str,
    msg: str,
    value: Any,
    context: dict[str, Any],
    suggestion: str,
) -> StoreValidationError:
    return StoreValidationError(
        [
            {
                "code": code,
                "loc": loc,
                "msg": msg,
                "severity": "error",
                "value": value,
                "context": context,
                "suggestion": suggestion,
            },
        ],
    )


def _positive_int(name: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return value


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 string")
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return timestamp


def _validate_page(limit: Any, offset: Any) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError(f"limit must be a positive integer, got {limit!r}")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ValueError(f"offset must be a non-negative integer, got {offset!r}")
