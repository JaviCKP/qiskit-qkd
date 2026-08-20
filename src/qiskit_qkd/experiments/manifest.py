"""Atomic, self-describing JSON/CSV experiment artifacts.

The persisted artifact (manifest plus CSV) is the reproducibility unit.  A
``SimulationResult`` is intentionally not coupled to filesystem paths or CSV
serialization; callers may persist it through this module at the experiment
boundary when they need a versioned record.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from .._json import JSONValue, normalize_json_value
from ..provenance import extract_seeds, scenario_provenance, vcs_provenance


@dataclass(frozen=True, slots=True)
class ArtifactPaths:
    """Paths written by :func:`write_artifact`."""

    manifest: Path
    csv: Path

    @property
    def manifest_path(self) -> Path:
        return self.manifest

    @property
    def csv_path(self) -> Path:
        return self.csv


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _atomic_write_pair(first: tuple[Path, bytes], second: tuple[Path, bytes]) -> None:
    """Commit two related files together, leaving no temporary debris on error.

    A manifest without its CSV (or vice versa) is not a reproducible artifact.
    Both payloads are therefore prepared and fsynced before either destination
    is replaced.  ``os.replace`` is still used for each final file because it
    is the only portable atomic primitive available on Windows and POSIX.
    """

    temporary_paths: list[Path] = []
    try:
        for destination, data in (first, second):
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(
                prefix=f".{destination.name}.", dir=destination.parent
            )
            temporary_path = Path(temporary)
            temporary_paths.append(temporary_path)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary_paths[0], first[0])
        os.replace(temporary_paths[1], second[0])
        temporary_paths.clear()
    finally:
        for temporary in temporary_paths:
            try:
                temporary.unlink()
            except OSError:
                pass


def _jsonable(value: Any) -> JSONValue:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
    if isinstance(value, Mapping):
        return normalize_json_value(value, path="artifact")
    if isinstance(value, (list, tuple)):
        return normalize_json_value(value, path="artifact")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _flatten_row(row: Mapping[str, Any]) -> dict[str, str | int | float | bool]:
    flattened: dict[str, str | int | float | bool] = {}
    for key, value in row.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            flattened[str(key)] = "" if value is None else value
        else:
            flattened[str(key)] = json.dumps(
                _jsonable(value),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
    return flattened


def _rows(rows: Iterable[Any]) -> list[dict[str, JSONValue]]:
    result: list[dict[str, JSONValue]] = []
    for item in rows:
        value = _jsonable(item)
        if isinstance(value, Mapping):
            result.append(dict(value))
        else:
            result.append({"value": value})
    return result


def _scenario_record(value: Any) -> dict[str, JSONValue]:
    """Normalize a scenario or an already extracted scenario record.

    Benchmarks often carry a scenario digest alongside their serialized
    payload.  Re-hashing that wrapper would hash the provenance metadata rather
    than the scenario itself, so a valid precomputed record is trusted as-is.
    """

    if isinstance(value, Mapping):
        canonical = value.get("canonical_json")
        digest = value.get("digest")
        if isinstance(canonical, str) and isinstance(digest, str):
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                return {"canonical_json": canonical, "digest": digest}
        # ``Scenario.digest`` deliberately ignores the transport schema marker
        # (v1 and v2 describe the same physical setup).  Rows commonly contain
        # ``Scenario.to_dict()`` rather than the object itself, so reproduce
        # that rule when hashing a serialized mapping.
        schema_version = value.get("schema_version")
        if isinstance(schema_version, int) and schema_version != 1:
            from .._json import dumps_canonical

            legacy = dict(value)
            legacy["schema_version"] = 1
            digest = hashlib.sha256(
                dumps_canonical(legacy).encode("utf-8")
            ).hexdigest()
            encoded = dumps_canonical(value)
            return {"canonical_json": encoded, "digest": digest}
    return scenario_provenance(value)


def _prepare_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    manifest_name: str,
) -> tuple[list[dict[str, JSONValue]], list[dict[str, JSONValue]]]:
    """Add stable row identity and links required by the manifest contract."""

    prepared: list[dict[str, JSONValue]] = []
    result_records: list[dict[str, JSONValue]] = []
    seen_ids: set[str] = set()
    for index, source in enumerate(rows, start=1):
        row = dict(source)
        result_id = row.get("result_id")
        if not isinstance(result_id, str) or not result_id.strip():
            result_id = f"result-{index:06d}"
        result_id = result_id.strip()
        if result_id in seen_ids:
            raise ValueError(f"duplicate result_id in artifact rows: {result_id!r}")
        seen_ids.add(result_id)
        row["result_id"] = result_id

        scenario = row.get("scenario")
        scenario_record: dict[str, JSONValue] | None = None
        if scenario is not None:
            scenario_record = _scenario_record(scenario)
            row["scenario_digest"] = scenario_record["digest"]

        # Ignore fields generated by a previous normalization pass; callers
        # may pass rows returned by ``_rows``/``write_artifact`` back in.
        seed_source = {
            key: value
            for key, value in row.items()
            if key not in {"seed_paths", "manifest_ref"}
        }
        seeds = extract_seeds(seed_source)
        row["seed_paths"] = json.dumps(
            seeds, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        if "seed" not in row:
            direct = [
                value
                for path, value in seeds.items()
                if path == "seed" or path.endswith(".seed")
            ]
            row["seed"] = direct[0] if len(direct) == 1 else ""
        row["manifest_ref"] = manifest_name
        prepared.append(row)
        result_records.append(
            {
                "result_id": result_id,
                "csv_row": index,
                "scenario_digest": row.get("scenario_digest", ""),
                "seed_paths": seeds,
            }
        )
    return prepared, result_records


def _csv_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    fields = sorted({str(key) for row in rows for key in row})
    if not fields:
        fields = ["value"]
    with tempfile.SpooledTemporaryFile(
        mode="w+", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(_flatten_row(row))
        stream.seek(0)
        return stream.read().encode("utf-8")


def _script_info(generator_path: str | os.PathLike[str] | None) -> dict[str, JSONValue]:
    path = Path(generator_path).resolve() if generator_path else None
    if path is None:
        frame = inspect.currentframe()
        caller = frame.f_back if frame is not None else None
        path = Path(caller.f_code.co_filename).resolve() if caller else None
    if path is not None and path.exists() and path.is_file():
        script_path = str(path)
        script_hash = _sha256(path)
    else:
        script_path = str(path) if path is not None else "unknown"
        script_hash = "unknown"
    return {
        "path": script_path,
        "sha256": script_hash,
        "command": [sys.executable, script_path, *sys.argv[1:]]
        if script_path != "unknown"
        else [sys.executable],
    }


def _versions() -> dict[str, JSONValue]:
    def version(name: str) -> str | None:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return None

    return {
        "python": sys.version,
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "qiskit": version("qiskit") or "unknown",
        "qiskit_aer": version("qiskit-aer"),
        "qiskit_aer_status": "available" if version("qiskit-aer") else "absent",
    }


def build_manifest(
    *,
    rows: Iterable[Any] = (),
    scenarios: Sequence[Any] | None = None,
    generator_path: str | os.PathLike[str] | None = None,
    command: Sequence[str] | None = None,
    csv_path: str | os.PathLike[str] | None = None,
    csv_sha256: str | None = None,
    repo_root: str | os.PathLike[str] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, JSONValue]:
    """Build a JSON-safe manifest before writing its companion files."""

    raw_rows = _rows(rows)
    materialized_rows, result_records = _prepare_rows(
        raw_rows,
        manifest_name=(
            Path(csv_path).with_suffix(".json").name
            if csv_path is not None
            else "manifest.json"
        ),
    )
    scenario_values = list(scenarios or [])
    if not scenario_values:
        scenario_values = [
            row["scenario"] for row in materialized_rows if "scenario" in row
        ]
    scenario_records = [_scenario_record(item) for item in scenario_values]
    # A row is itself a result-bearing scenario.  Include every one even when
    # callers supplied a de-duplicated scenario list.
    for row in materialized_rows:
        if "scenario" not in row:
            continue
        record = _scenario_record(row["scenario"])
        if record not in scenario_records:
            scenario_records.append(record)
    seed_payload: dict[str, JSONValue] = {}
    for item in [*scenario_values, *materialized_rows]:
        seed_item = (
            {
                key: value
                for key, value in item.items()
                if key not in {"seed_paths", "manifest_ref"}
            }
            if isinstance(item, Mapping)
            else item
        )
        seed_payload.update(extract_seeds(seed_item))
    script = _script_info(generator_path)
    if command is not None:
        script["command"] = list(command)
    git = vcs_provenance(repo_root)
    runtime = _versions()
    csv_record: dict[str, JSONValue] = {
        "path": str(csv_path) if csv_path is not None else "results.csv",
        "sha256": csv_sha256 or "unknown",
        "row_count": len(materialized_rows),
        "rows": len(materialized_rows),
    }
    canonical_scenarios = [record["canonical_json"] for record in scenario_records]
    digests = [record["digest"] for record in scenario_records]
    return {
        "schema_version": 1,
        "generated_at_utc": generated_at_utc or _utc_now(),
        "runtime": runtime,
        "git": git,
        "commit_confidence": git.get("confidence", "none"),
        "commit_verified": git.get("commit_verified", False),
        "generator": script,
        "seeds": seed_payload,
        "scenarios": scenario_records,
        # Singular aliases make one-scenario manifests convenient while the
        # list remains lossless for sweeps.
        "scenario_canonical_json": (
            canonical_scenarios[0]
            if len(canonical_scenarios) == 1
            else canonical_scenarios
        ),
        "scenario_digest": digests[0] if len(digests) == 1 else digests,
        "csv": csv_record,
        "csv_sha256": csv_record["sha256"],
        "csv_row_count": len(materialized_rows),
        "csv_rows": len(materialized_rows),
        "commit": git["commit"],
        "dirty": git["dirty"],
        "versions": runtime,
        "script_path": script["path"],
        "script_sha256": script["sha256"],
        "command": script["command"],
        # Full observations remain available for compatibility; ``result_ids``
        # and ``results`` make the one-to-one CSV coverage explicit.
        "result_ids": [record["result_id"] for record in result_records],
        "results": result_records,
        "observations": materialized_rows,
    }


def write_artifact(
    output_dir: str | os.PathLike[str],
    *,
    name: str = "experiment",
    rows: Iterable[Any] = (),
    scenarios: Sequence[Any] | None = None,
    generator_path: str | os.PathLike[str] | None = None,
    command: Sequence[str] | None = None,
    repo_root: str | os.PathLike[str] | None = None,
    generated_at_utc: str | None = None,
) -> ArtifactPaths:
    """Atomically write ``<name>.json`` and ``<name>.csv`` with hashes.

    Every CSV row receives a stable ``result_id`` and scenario/seed links, and
    the manifest enumerates those IDs.  This is deliberately an explicit
    persistence boundary rather than a requirement on in-memory results.
    """

    directory = Path(output_dir)
    safe_name = Path(name).name
    manifest_path = directory / f"{safe_name}.json"
    csv_path = directory / f"{safe_name}.csv"
    raw_rows = _rows(rows)
    materialized_rows, _result_records = _prepare_rows(
        raw_rows, manifest_name=manifest_path.name
    )
    csv_data = _csv_bytes(materialized_rows)
    manifest = build_manifest(
        rows=materialized_rows,
        scenarios=scenarios,
        generator_path=generator_path,
        command=command,
        csv_path=csv_path.name,
        csv_sha256=hashlib.sha256(csv_data).hexdigest(),
        repo_root=repo_root,
        generated_at_utc=generated_at_utc,
    )
    encoded = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _atomic_write_pair((csv_path, csv_data), (manifest_path, encoded))
    return ArtifactPaths(manifest=manifest_path, csv=csv_path)


# Descriptive aliases for callers that prefer explicit terminology.
write_experiment_artifact = write_artifact
create_manifest = build_manifest

__all__ = [
    "ArtifactPaths",
    "build_manifest",
    "create_manifest",
    "write_artifact",
    "write_experiment_artifact",
]
