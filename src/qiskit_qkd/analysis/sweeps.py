"""Parameter sweep helpers with JSON-safe outputs."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from typing import Any, Protocol

from qiskit_qkd._json import normalize_json_object, normalize_json_value
from qiskit_qkd.analysis.metrics import metric_rows_from_results
from qiskit_qkd.config import (
    Scenario,
    require_effective_target,
    require_time_evolution,
)
from qiskit_qkd.temporal import ParameterResolver

BackendFactory = Callable[[Scenario], Any]
SweepValue = float | int | bool | None
SweepRow = dict[str, Any]

COMPACT_SWEEP_SCHEMA_VERSION = 2
_COMPACT_METADATA_FIELDS = frozenset(
    {"provenance", "assessment", "effective_model"},
)
_PATH_SEPARATOR = "\x1f"
_MISSING = object()
_COMPACT_ROW_INVARIANT_FIELDS = frozenset(
    {
        "abort_is_legacy",
        "channel_kind",
        "composable",
        "data_status",
        "finite_key",
        "key_status",
        "protocol",
        "qber_method",
        "rate_estimate_method",
        "rate_estimate_status",
        "security_scope",
        "source_kind",
        "target",
        "threshold",
        "threshold_decision_source",
        "verification_status",
    },
)


class BB84Runner(Protocol):
    def run(self, scenario: Scenario, backend: Any | None = None) -> Any:
        """Run a BB84-compatible protocol and return a result object."""
        ...


def sweep_bb84_distance(
    protocol: BB84Runner,
    scenario: Scenario,
    distances_km: Iterable[float],
    *,
    repeats: int = 1,
    backend_factory: BackendFactory | None = None,
) -> list[SweepRow]:
    """Run BB84 for each distance and return JSON-safe metric rows."""

    _require_positive_repeats(repeats)

    require_effective_target(scenario, "channel.distance_km")
    requested_digest = scenario.digest()
    rows: list[SweepRow] = []
    for distance_km in distances_km:
        for repeat in range(repeats):
            run_scenario = replace(
                scenario,
                seed=scenario.seed + repeat,
                channel=replace(scenario.channel, distance_km=float(distance_km)),
            )
            backend = None if backend_factory is None else backend_factory(run_scenario)
            result = protocol.run(run_scenario, backend=backend)
            row = _result_row(
                result,
                requested_scenario_digest=requested_digest,
                qber_abort_threshold=run_scenario.post_processing.qber_abort_threshold,
            )
            row.update(
                {
                    "distance_km": float(distance_km),
                    "repeat": repeat,
                    "seed": run_scenario.seed,
                },
            )
            rows.append(row)
    return rows


def sweep_bb84_time(
    protocol: BB84Runner,
    scenario: Scenario,
    time_points_s: Iterable[float],
    *,
    repeats: int = 1,
    backend_factory: BackendFactory | None = None,
    resolver: ParameterResolver | None = None,
) -> list[SweepRow]:
    """Run BB84 at selected times using the scenario's dynamic schedules."""

    _require_positive_repeats(repeats)

    raw_time_points = tuple(time_points_s)
    require_time_evolution(scenario, raw_time_points)
    time_points = tuple(float(time_s) for time_s in raw_time_points)
    active_resolver = resolver or ParameterResolver()
    requested_digest = scenario.digest()
    rows: list[SweepRow] = []
    for time_s in time_points:
        effective = active_resolver.scenario_at(scenario, time_s=float(time_s))
        dynamic_values = active_resolver.parameter_values(
            scenario,
            time_s=float(time_s),
        )
        for repeat in range(repeats):
            run_scenario = replace(
                effective,
                seed=scenario.seed + repeat,
            )
            backend = None if backend_factory is None else backend_factory(run_scenario)
            result = protocol.run(run_scenario, backend=backend)
            row = _result_row(
                result,
                requested_scenario_digest=requested_digest,
                qber_abort_threshold=run_scenario.post_processing.qber_abort_threshold,
            )
            row.update(
                {
                    "time_s": float(time_s),
                    "resolution_time_s": float(time_s),
                    "repeat": repeat,
                    "seed": run_scenario.seed,
                }
            )
            row.update(dynamic_values)
            rows.append(row)
    return rows


def sweep_scenario_parameter(
    protocol: BB84Runner,
    scenario: Scenario,
    target: str,
    values: Iterable[SweepValue],
    *,
    repeats: int = 1,
    backend_factory: BackendFactory | None = None,
) -> list[SweepRow]:
    """Run a protocol while sweeping any registered scenario target."""

    _require_positive_repeats(repeats)
    normalized_target = require_effective_target(scenario, target)

    requested_digest = scenario.digest()
    rows: list[SweepRow] = []
    for value in values:
        normalized_value = _normalize_sweep_value(normalized_target, value)
        for repeat in range(repeats):
            run_scenario = _replace_target(
                replace(scenario, seed=scenario.seed + repeat),
                normalized_target,
                normalized_value,
            )
            backend = None if backend_factory is None else backend_factory(run_scenario)
            result = protocol.run(run_scenario, backend=backend)
            row = _result_row(
                result,
                requested_scenario_digest=requested_digest,
                qber_abort_threshold=run_scenario.post_processing.qber_abort_threshold,
            )
            row["target"] = normalized_target
            row[normalized_target] = normalized_value
            row["repeat"] = repeat
            rows.append(row)
    return rows


def _require_positive_repeats(repeats: int) -> None:
    if not isinstance(repeats, int) or isinstance(repeats, bool):
        raise TypeError("repeats must be a positive integer")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")


def _replace_target(scenario: Scenario, target: str, value: Any) -> Scenario:
    section, field = target.split(".")
    if section == "scenario":
        return replace(scenario, **{field: value})
    section_config = getattr(scenario, section)
    return replace(scenario, **{section: replace(section_config, **{field: value})})


def _normalize_sweep_value(target: str, value: SweepValue) -> SweepValue:
    if target != "scenario.pulses" or isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _result_row(
    result: Any,
    *,
    requested_scenario_digest: str,
    qber_abort_threshold: float | None,
) -> SweepRow:
    row: SweepRow = dict(
        metric_rows_from_results(
            [result],
            label_key="run",
            qber_abort_threshold=qber_abort_threshold,
        )[0],
    )
    row.pop("run", None)
    assessment = _mapping_payload(getattr(result, "assessment", None))
    qber_defined = bool(assessment.get("qber_defined", result.metrics.sifted > 0))
    qber_value = assessment.get("qber_value") if qber_defined else None
    row["qber_defined"] = qber_defined
    row["qber"] = qber_value
    row["assessment"] = assessment
    provenance = _mapping_payload(getattr(result, "provenance", None))
    row["provenance"] = provenance
    row["requested_scenario_digest"] = requested_scenario_digest
    row["effective_scenario_digest"] = result.scenario.digest()
    effective_model = provenance.get("effective_model")
    if isinstance(effective_model, Mapping):
        row["effective_model"] = dict(effective_model)
    return row


def _mapping_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return normalize_json_object(value, path="result metadata")
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return normalize_json_object(payload, path="result metadata")
    return {}


def compact_sweep_payload(
    rows: Iterable[Mapping[str, Any]],
    *,
    requested_scenario_digest: str | None = None,
    summary: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a compact, metadata-factorized representation of sweep rows.

    Scientific sweep helpers continue to return the complete row list.  This
    additive DTO is for panel/API persistence only: scalar axes, repetition,
    seeds, and metrics remain in input order while repeated provenance,
    assessment, and effective-model fields are factored into shared values and
    column arrays.  ``expand_compact_sweep_rows`` reconstructs the original
    row shape for compatibility or archival checks.
    """

    source_rows = [dict(row) for row in rows]
    provenance_rows: list[dict[str, Any]] = []
    assessment_rows: list[dict[str, Any]] = []
    model_rows: list[dict[str, Any]] = []
    compact_rows: list[SweepRow] = []
    inferred_digest = requested_scenario_digest

    for source in source_rows:
        if inferred_digest is None:
            candidate = source.get("requested_scenario_digest")
            if isinstance(candidate, str):
                inferred_digest = candidate

        provenance = _mapping_payload(source.get("provenance"))
        model = _mapping_payload(source.get("effective_model"))
        if not model:
            model = _mapping_payload(provenance.get("effective_model"))
        provenance.pop("effective_model", None)
        assessment = _mapping_payload(source.get("assessment"))
        provenance_rows.append(provenance)
        assessment_rows.append(assessment)
        model_rows.append(model)

        compact: SweepRow = {}
        for key, value in source.items():
            if key in _COMPACT_METADATA_FIELDS or key == "requested_scenario_digest":
                continue
            if isinstance(value, Mapping | list | tuple):
                # Nested result/scenario/event/circuit payloads are deliberately
                # omitted from rows; metadata is represented in the columns
                # below and can be reconstructed on demand.
                continue
            compact[key] = normalize_json_value(value, path=f"sweep row.{key}")

        compact_rows.append(compact)

    row_invariants, compact_rows = _factor_row_invariants(compact_rows)
    provenance_shared, provenance_columns, provenance_missing = _factor_metadata(
        provenance_rows,
    )
    assessment_shared, assessment_columns, assessment_missing = _factor_metadata(
        assessment_rows,
    )
    model_shared, model_columns, model_missing = _factor_metadata(model_rows)
    payload: dict[str, Any] = {
        "schema_version": COMPACT_SWEEP_SCHEMA_VERSION,
        "row_encoding": "scalar-records-v1",
        "row_count": len(compact_rows),
        "requested_scenario_digest": inferred_digest,
        "provenance": provenance_shared,
        "assessment": assessment_shared,
        "effective_model": model_shared,
        "row_invariants": row_invariants,
        "rows": compact_rows,
    }
    if provenance_columns:
        payload["provenance_columns"] = provenance_columns
    if provenance_missing:
        payload["provenance_missing"] = provenance_missing
    if assessment_columns:
        payload["assessment_columns"] = assessment_columns
    if assessment_missing:
        payload["assessment_missing"] = assessment_missing
    if model_columns:
        payload["effective_model_columns"] = model_columns
    if model_missing:
        payload["effective_model_missing"] = model_missing
    if summary is not None:
        summary_rows = [dict(row) for row in summary]
        # Summary fields are scientifically meaningful and remain lossless;
        # only their repeated object keys are factored into columns.
        payload["summary"] = _compact_summary_rows(summary_rows)
    return payload


def expand_compact_sweep_rows(payload: Mapping[str, Any]) -> list[SweepRow]:
    """Expand a compact panel sweep DTO into the scientific row shape.

    Legacy payloads without ``schema_version=2`` are returned as defensive
    row copies.  Compact payloads merge shared metadata and per-row columns,
    restoring the nested ``effective_model`` inside provenance as emitted by
    :func:`sweep_scenario_parameter`.
    """

    raw_rows = payload.get("rows", [])
    if not isinstance(raw_rows, list):
        raise TypeError("compact sweep rows must be a list")
    if payload.get("schema_version") != COMPACT_SWEEP_SCHEMA_VERSION:
        return [
            normalize_json_object(row, path="sweep row")
            for row in raw_rows
            if isinstance(row, Mapping)
        ]
    raw_count = payload.get("row_count", len(raw_rows))
    if (
        not isinstance(raw_count, int)
        or isinstance(raw_count, bool)
        or raw_count < 0
        or raw_count != len(raw_rows)
    ):
        raise ValueError("compact sweep row_count must match rows")

    shared_provenance = _mapping_payload(payload.get("provenance"))
    row_invariants = _mapping_payload(payload.get("row_invariants"))
    provenance_columns = _mapping_payload(payload.get("provenance_columns"))
    provenance_missing = _mapping_payload(payload.get("provenance_missing"))
    shared_assessment = _mapping_payload(payload.get("assessment"))
    assessment_columns = _mapping_payload(payload.get("assessment_columns"))
    assessment_missing = _mapping_payload(payload.get("assessment_missing"))
    shared_model = _mapping_payload(payload.get("effective_model"))
    model_columns = _mapping_payload(payload.get("effective_model_columns"))
    model_missing = _mapping_payload(payload.get("effective_model_missing"))
    requested_digest = payload.get("requested_scenario_digest")
    expanded: list[SweepRow] = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise TypeError(f"compact sweep row {index} must be an object")
        row = normalize_json_object(raw_row, path=f"sweep row[{index}]")
        for key, value in row_invariants.items():
            row.setdefault(key, value)
        provenance = _expand_metadata(
            shared_provenance,
            provenance_columns,
            provenance_missing,
            index,
        )
        assessment = _expand_metadata(
            shared_assessment,
            assessment_columns,
            assessment_missing,
            index,
        )
        model = _expand_metadata(
            shared_model,
            model_columns,
            model_missing,
            index,
        )
        if provenance:
            if model:
                provenance["effective_model"] = model
            row["provenance"] = provenance
        if assessment:
            row["assessment"] = assessment
        if model:
            row["effective_model"] = model
        if isinstance(requested_digest, str):
            row["requested_scenario_digest"] = requested_digest
        expanded.append(row)
    return expanded


def _factor_row_invariants(
    rows: list[SweepRow],
) -> tuple[dict[str, Any], list[SweepRow]]:
    if not rows:
        return {}, rows
    invariants: dict[str, Any] = {}
    for key in _COMPACT_ROW_INVARIANT_FIELDS:
        values = [row.get(key, _MISSING) for row in rows]
        if values[0] is _MISSING or any(value is _MISSING for value in values[1:]):
            continue
        normalized = [
            normalize_json_value(value, path=f"sweep row.{key}")
            for value in values
        ]
        if _all_equal(normalized):
            invariants[key] = normalized[0]
    if not invariants:
        return {}, rows
    return invariants, [
        {key: value for key, value in row.items() if key not in invariants}
        for row in rows
    ]


def expand_compact_sweep_summary(value: Any) -> list[SweepRow]:
    """Expand a columnar compact summary, accepting legacy summary lists."""

    if isinstance(value, list):
        return [
            normalize_json_object(row, path="sweep summary row")
            for row in value
            if isinstance(row, Mapping)
        ]
    if not isinstance(value, Mapping):
        raise TypeError("sweep summary must be a list or compact object")
    if value.get("schema_version") != COMPACT_SWEEP_SCHEMA_VERSION:
        raise ValueError("unsupported compact sweep summary schema")
    raw_count = value.get("row_count")
    columns = value.get("columns")
    missing = value.get("missing", {})
    if not isinstance(raw_count, int) or isinstance(raw_count, bool) or raw_count < 0:
        raise ValueError("compact sweep summary row_count must be non-negative")
    if not isinstance(columns, Mapping) or not isinstance(missing, Mapping):
        raise TypeError("compact sweep summary columns and missing must be objects")
    output = [dict() for _ in range(raw_count)]
    for key, raw_values in columns.items():
        if not isinstance(key, str) or not isinstance(raw_values, list):
            raise TypeError("compact sweep summary columns must map strings to lists")
        omitted = missing.get(key, [])
        if not isinstance(omitted, list):
            raise TypeError("compact sweep summary missing indexes must be a list")
        omitted_indexes = set(omitted)
        for index, item in enumerate(raw_values[:raw_count]):
            if index not in omitted_indexes:
                output[index][key] = normalize_json_value(
                    item,
                    path=f"sweep summary.{key}",
                )
    return output


def _factor_metadata(
    mappings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, list[int]]]:
    if not mappings:
        return {}, {}, {}
    shared: dict[str, Any] = {}
    columns: dict[str, Any] = {}
    missing: dict[str, list[int]] = {}
    flattened = [dict(_flatten_mapping(mapping)) for mapping in mappings]
    paths = sorted({path for mapping in flattened for path in mapping})
    for path in paths:
        values = [mapping.get(path, _MISSING) for mapping in flattened]
        present = [value is not _MISSING for value in values]
        normalized = [
            None if value is _MISSING else normalize_json_value(
                value,
                path=f"sweep metadata.{_PATH_SEPARATOR.join(path)}",
            )
            for value in values
        ]
        if all(present) and _all_equal(normalized):
            _assign_path(shared, path, normalized[0])
            continue
        if any(present):
            encoded_values = [
                _encode_metadata_column(value) if is_present else None
                for value, is_present in zip(normalized, present, strict=True)
            ]
            columns[_PATH_SEPARATOR.join(path)] = _compact_metadata_column(
                encoded_values,
            )
            absent_indexes = [
                index
                for index, is_present in enumerate(present)
                if not is_present
            ]
            if absent_indexes:
                missing[_PATH_SEPARATOR.join(path)] = absent_indexes
    return shared, columns, missing


def _compact_summary_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = sorted({key for row in rows for key in row})
    columns: dict[str, list[Any]] = {}
    missing: dict[str, list[int]] = {}
    for key in keys:
        values: list[Any] = []
        omitted: list[int] = []
        for index, row in enumerate(rows):
            if key not in row:
                values.append(None)
                omitted.append(index)
            else:
                values.append(
                    normalize_json_value(row[key], path=f"sweep summary.{key}"),
                )
        columns[key] = values
        if omitted:
            missing[key] = omitted
    result: dict[str, Any] = {
        "schema_version": COMPACT_SWEEP_SCHEMA_VERSION,
        "row_count": len(rows),
        "columns": columns,
    }
    if missing:
        result["missing"] = missing
    return result


def _expand_metadata(
    shared: Mapping[str, Any],
    columns: Mapping[str, Any],
    missing: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path, value in _flatten_mapping(shared):
        _assign_path(result, path, normalize_json_value(value, path="sweep metadata"))
    for raw_path, raw_values in columns.items():
        if not isinstance(raw_path, str):
            raise TypeError("compact sweep metadata paths must be strings")
        value = _metadata_column_value(raw_values, index=index)
        if value is _MISSING:
            continue
        raw_missing = missing.get(raw_path, [])
        if isinstance(raw_missing, list) and index in raw_missing:
            continue
        path = tuple(raw_path.split(_PATH_SEPARATOR))
        _assign_path(
            result,
            path,
            _decode_metadata_column(value, path=f"sweep metadata.{raw_path}"),
        )
    return result


def _encode_metadata_column(value: Any) -> Any:
    return normalize_json_value(value, path="sweep metadata column")


def _compact_metadata_column(values: list[Any]) -> Any:
    """Dictionary-encode repeated metadata values when it is smaller."""

    dictionary: list[Any] = []
    indexes: list[int] = []
    positions: dict[str, int] = {}
    for value in values:
        token = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        position = positions.get(token)
        if position is None:
            position = len(dictionary)
            positions[token] = position
            dictionary.append(value)
        indexes.append(position)
    candidate = {
        "encoding": "dictionary-v1",
        "values": dictionary,
        "indexes": indexes,
    }
    if _encoded_size(candidate) < _encoded_size(values):
        return candidate
    return values


def _metadata_column_value(value: Any, *, index: int) -> Any:
    if isinstance(value, list):
        return value[index] if index < len(value) else _MISSING
    if not isinstance(value, Mapping):
        raise TypeError("compact sweep metadata columns must be arrays or objects")
    if value.get("encoding") != "dictionary-v1":
        raise ValueError("unsupported compact sweep metadata column encoding")
    dictionary = value.get("values")
    indexes = value.get("indexes")
    if not isinstance(dictionary, list) or not isinstance(indexes, list):
        raise TypeError("dictionary metadata columns require values and indexes arrays")
    if index >= len(indexes):
        return _MISSING
    position = indexes[index]
    if (
        not isinstance(position, int)
        or isinstance(position, bool)
        or position < 0
        or position >= len(dictionary)
    ):
        raise ValueError("dictionary metadata column index is out of range")
    return dictionary[position]


def _encoded_size(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )


def _decode_metadata_column(value: Any, *, path: str) -> Any:
    return normalize_json_value(value, path=path)


def _flatten_mapping(
    value: Mapping[str, Any],
    prefix: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], Any]]:
    items: list[tuple[tuple[str, ...], Any]] = []
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("sweep metadata keys must be strings")
        path = (*prefix, key)
        if isinstance(item, Mapping) and item:
            items.extend(_flatten_mapping(item, path))
        else:
            items.append((path, item))
    return items


def _assign_path(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    if not path:
        return
    current = target
    for key in path[:-1]:
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    current[path[-1]] = value


def _all_equal(values: list[Any]) -> bool:
    if not values:
        return True
    first = json.dumps(
        values[0],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return all(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        == first
        for value in values[1:]
    )
