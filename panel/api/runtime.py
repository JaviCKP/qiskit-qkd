from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from qiskit_qkd._json import normalize_json_object
from qiskit_qkd.analysis import (
    compact_sweep_payload,
    summarize_metric_rows,
    sweep_bb84_time,
    sweep_scenario_parameter,
)
from qiskit_qkd.channels import channel_state_from_scenario
from qiskit_qkd.config import (
    CapabilityError,
    CapabilityIssue,
    Scenario,
    UnsupportedScenarioVersionError,
    builtin_presets,
    capability_issues,
    require_effective_target,
    require_executable_scenario,
    require_time_evolution,
)
from qiskit_qkd.config.dynamics import validate_parameter_target
from qiskit_qkd.detectors import detector_state_from_scenario
from qiskit_qkd.protocols import BB84Protocol, E91Protocol
from qiskit_qkd.sources import source_state_from_scenario
from qiskit_qkd.temporal import ParameterResolver
from qiskit_qkd.timing import timing_state_from_scenario

from .costs import (
    estimate_run_cost,
    estimate_sweep_cost,
    require_operational_payload,
    require_operational_scenario,
)
from .errors import ApiValidationError, api_validation_error
from .jobs import JobControl
from .limits import DEFAULT_OPERATIONAL_LIMITS, OperationalLimits

# Hard ceiling for axis_points * series_points * repeats. This bounds both
# request-time validation work and the number of protocol executions per job.
MAX_SWEEP_EVALUATIONS = DEFAULT_OPERATIONAL_LIMITS.max_sweep_evaluations


def scenario_from_body(
    body: Mapping[str, Any],
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> Scenario:
    require_operational_payload(body, limits=limits)
    scenario_data = body.get("scenario", body)
    if not isinstance(scenario_data, Mapping):
        raise ApiValidationError(
            [{"loc": "scenario", "msg": "scenario must be an object"}],
        )
    errors = [
        {"loc": field, "msg": f"{field} is required"}
        for field in ("pulses", "clock_rate_hz", "seed")
        if field not in scenario_data
    ]
    for section in (
        "protocol",
        "source",
        "channel",
        "detector",
        "timing",
        "post_processing",
        "eavesdropper",
        "e91",
        "dynamic",
        "metadata",
    ):
        if section in scenario_data and not isinstance(scenario_data[section], Mapping):
            errors.append(
                {"loc": section, "msg": f"{section} must be an object"},
            )
    if errors:
        raise ApiValidationError(errors)
    try:
        scenario = Scenario.from_dict(scenario_data)
        require_executable_scenario(scenario)
        require_operational_scenario(scenario, limits=limits)
        return scenario
    except UnsupportedScenarioVersionError as exc:
        # Preserve the version metadata so clients can select a migration or
        # upgrade path without scraping an error string.
        raise ApiValidationError(
            [
                {
                    "loc": "scenario.schema_version",
                    "code": "UNSUPPORTED_SCENARIO_VERSION",
                    "msg": str(exc),
                    "found_version": exc.found_version,
                    "supported_versions": list(exc.supported_versions),
                    "suggestion": exc.suggestion,
                },
            ],
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise api_validation_error(exc, payload=scenario_data) from exc


def run_scenario_job(
    scenario_data: Mapping[str, Any],
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
    *,
    job_control: JobControl | None = None,
) -> dict[str, Any]:
    if job_control is not None:
        job_control.checkpoint()
    requested_scenario = Scenario.from_dict(scenario_data)
    require_executable_scenario(requested_scenario)
    requested_digest = requested_scenario.digest()
    scenario = _cap_event_sample(
        ParameterResolver().scenario_at(requested_scenario, time_s=0.0),
        limits=limits,
    )
    protocol = _protocol_for(scenario)
    result = protocol.run(
        scenario,
        cancellation_check=(
            job_control.checkpoint if job_control is not None else None
        ),
    )
    if job_control is not None:
        job_control.checkpoint()
    result_summary = normalize_json_object(
        result.summary(),
        path="result_summary",
    )
    result_payload = _result_payload(result.to_dict())
    _annotate_payload_provenance(
        result_summary,
        requested_scenario_digest=requested_digest,
        effective_scenario_digest=result.scenario.digest(),
        resolution_time_s=0.0,
    )
    _annotate_payload_provenance(
        result_payload,
        requested_scenario_digest=requested_digest,
        effective_scenario_digest=result.scenario.digest(),
        resolution_time_s=0.0,
    )
    return {
        "result_summary": result_summary,
        "result": result_payload,
    }


def validate_sweep_request(
    scenario: Scenario,
    axis: Mapping[str, Any],
    series: Mapping[str, Any] | None,
    repeats: int,
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> tuple[list[float | int | bool | None], list[float | int | bool | None] | None]:
    """Validate a complete sweep before it is submitted to a worker."""

    require_executable_scenario(scenario)
    require_operational_scenario(scenario, limits=limits)
    _require_known_fields(axis, {"target", "values", "time_axis"}, loc="axis")
    if series is not None:
        _require_known_fields(series, {"target", "values"}, loc="series")
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="SWEEP_REPEATS_INVALID",
                    loc="repeats",
                    msg=(f"Sweep repeats must be a positive integer, got {repeats!r}."),
                    severity="error",
                    value=repeats,
                    context={},
                    suggestion="Set repeats to an integer greater than or equal to 1.",
                ),
            ],
        )
    if repeats > limits.max_repeats:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="SWEEP_REPEAT_LIMIT_EXCEEDED",
                    loc="repeats",
                    msg=(
                        f"Sweep requests {repeats} repeats; the limit is "
                        f"{limits.max_repeats}."
                    ),
                    severity="error",
                    value=repeats,
                    context={"max_repeats": limits.max_repeats},
                    suggestion=f"Reduce repeats to at most {limits.max_repeats}.",
                ),
            ],
        )
    axis_values = parse_axis_values(
        axis.get("values"),
        loc="axis.values",
        limits=limits,
    )
    raw_time_axis = axis.get("time_axis", False)
    if not isinstance(raw_time_axis, bool):
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TIME_AXIS_FLAG_INVALID",
                    loc="axis.time_axis",
                    msg=(
                        "axis.time_axis must be a boolean when provided, "
                        f"got {raw_time_axis!r}."
                    ),
                    severity="error",
                    value=raw_time_axis,
                    context={},
                    suggestion="Use true/false, or omit axis.time_axis.",
                ),
            ],
        )
    explicit_time_axis = raw_time_axis
    raw_axis_target = axis.get("target")
    if explicit_time_axis and raw_axis_target not in {None, "time_s"}:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TIME_AXIS_TARGET_CONFLICT",
                    loc="axis.target",
                    msg=(
                        "axis.time_axis=true conflicts with target "
                        f"{raw_axis_target!r}."
                    ),
                    severity="error",
                    value=raw_axis_target,
                    context={"time_axis": True},
                    suggestion="Set axis.target to 'time_s' or remove time_axis.",
                ),
            ],
        )
    time_axis = explicit_time_axis or raw_axis_target == "time_s"
    if time_axis:
        if series is not None:
            raise CapabilityError(
                [
                    CapabilityIssue(
                        code="TIME_SERIES_UNSUPPORTED",
                        loc="series",
                        msg="time_s sweeps cannot be combined with a series axis.",
                        severity="error",
                        value=dict(series),
                        context={"axis_target": "time_s"},
                        suggestion=(
                            "Remove series, or use a static parameter as the axis."
                        ),
                    ),
                ],
            )
        _require_sweep_size(axis_values, None, repeats, limits=limits)
        require_time_evolution(scenario, axis_values)
        estimate_sweep_cost(
            scenario,
            axis,
            None,
            repeats,
            axis_values,
            None,
            limits=limits,
        )
        return axis_values, None

    axis_target = _registered_sweep_target(scenario, raw_axis_target, "axis")
    axis_values = _normalize_target_values(
        axis_target,
        axis_values,
        generated_from_range=isinstance(axis.get("values"), Mapping),
        loc="axis.values",
    )
    series_values = None
    series_target = None
    if series is not None:
        series_target = _registered_sweep_target(
            scenario,
            series.get("target"),
            "series",
        )
        if series_target == axis_target:
            raise CapabilityError(
                [
                    CapabilityIssue(
                        code="AXIS_SERIES_TARGET_CONFLICT",
                        loc="series.target",
                        msg=f"Axis and series both target {axis_target!r}.",
                        severity="error",
                        value=series_target,
                        context={"axis_target": axis_target},
                        suggestion=(
                            "Choose two different effective targets, or remove series."
                        ),
                    ),
                ],
            )
        series_values = parse_axis_values(
            series.get("values"),
            loc="series.values",
            limits=limits,
        )
        series_values = _normalize_target_values(
            series_target,
            series_values,
            generated_from_range=isinstance(series.get("values"), Mapping),
            loc="series.values",
        )

    _require_sweep_size(axis_values, series_values, repeats, limits=limits)
    effective = ParameterResolver().scenario_at(scenario, time_s=0.0)
    _validate_target_values(effective, axis_target, axis_values, loc="axis.values")
    if series_target is None or series_values is None:
        require_effective_target(effective, axis_target, purpose="axis")
        estimate_sweep_cost(
            scenario,
            axis,
            None,
            repeats,
            axis_values,
            None,
            limits=limits,
        )
        return axis_values, None

    _validate_target_values(
        effective,
        series_target,
        series_values,
        loc="series.values",
    )
    for series_value in series_values:
        series_scenario = set_target(effective, series_target, series_value)
        # The worker validates the axis after fixing each series value. Mirror
        # that exact order here so no accepted request can fail asynchronously.
        require_effective_target(series_scenario, axis_target, purpose="axis")

        # A series is meaningful when it is consumed for at least one point on
        # the axis. This also permits mutually dependent axes (for example
        # attenuation over positive distance) without judging only the base.
        series_issue: CapabilityError | None = None
        for axis_value in axis_values:
            point_scenario = set_target(series_scenario, axis_target, axis_value)
            try:
                require_effective_target(
                    point_scenario,
                    series_target,
                    purpose="series",
                )
            except CapabilityError as exc:
                series_issue = exc
            else:
                break
        else:
            assert series_issue is not None
            raise series_issue
    estimate_sweep_cost(
        scenario,
        axis,
        series,
        repeats,
        axis_values,
        series_values,
        limits=limits,
    )
    return axis_values, series_values


def sweep_scenario_job(
    scenario_data: Mapping[str, Any],
    axis: Mapping[str, Any],
    series: Mapping[str, Any] | None,
    repeats: int,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
    *,
    job_control: JobControl | None = None,
) -> dict[str, Any]:
    if job_control is not None:
        job_control.checkpoint()
    requested_scenario = Scenario.from_dict(scenario_data)
    requested_digest = requested_scenario.digest()
    axis_values, series_values = validate_sweep_request(
        requested_scenario,
        axis,
        series,
        repeats,
        limits=limits,
    )
    base_protocol = _protocol_for(requested_scenario)
    protocol = (
        _ProgressReportingProtocol(base_protocol, job_control)
        if job_control is not None
        else base_protocol
    )
    time_axis = bool(axis.get("time_axis") or axis.get("target") == "time_s")
    if time_axis:
        rows = sweep_bb84_time(
            protocol,
            requested_scenario,
            axis_values,
            repeats=repeats,
        )
        _annotate_sweep_rows(rows, requested_scenario_digest=requested_digest)
        summary = summarize_metric_rows(
            rows,
            group_by=("time_s",),
            metrics=("qber", "secret_key_rate_bps", "gain", "detected"),
        )
        return _sweep_result_payload(
            rows,
            summary,
            requested_scenario_digest=requested_digest,
        )

    scenario = ParameterResolver().scenario_at(requested_scenario, time_s=0.0)
    axis_target = validate_parameter_target(str(axis["target"]))
    group_by = [axis_target]
    all_rows: list[dict[str, Any]] = []
    if series is None:
        all_rows.extend(
            sweep_scenario_parameter(
                protocol,
                scenario,
                axis_target,
                axis_values,
                repeats=repeats,
            ),
        )
    else:
        series_target = validate_parameter_target(str(series["target"]))
        group_by.append(series_target)
        assert series_values is not None
        for series_value in series_values:
            series_scenario = set_target(scenario, series_target, series_value)
            rows = sweep_scenario_parameter(
                protocol,
                series_scenario,
                axis_target,
                axis_values,
                repeats=repeats,
            )
            for row in rows:
                row[series_target] = series_value
            all_rows.extend(rows)
    _annotate_sweep_rows(
        all_rows,
        requested_scenario_digest=requested_digest,
        resolution_time_s=0.0,
    )
    summary = summarize_metric_rows(
        all_rows,
        group_by=tuple(group_by),
        metrics=("qber", "secret_key_rate_bps", "gain", "detected"),
    )
    return _sweep_result_payload(
        all_rows,
        summary,
        requested_scenario_digest=requested_digest,
    )


def _sweep_result_payload(
    rows: list[dict[str, Any]],
    summary: list[dict[str, Any]],
    *,
    requested_scenario_digest: str,
) -> dict[str, Any]:
    """Return the versioned compact DTO for every panel sweep.

    Small results retain a tiny per-row resolution-time projection for legacy
    panel readers; heavy provenance, assessment, and effective-model metadata
    remain factorized at the envelope level regardless of sweep size.
    """

    return compact_sweep_payload(
        rows,
        requested_scenario_digest=requested_scenario_digest,
        summary=summary,
    )


def characterize_section(
    section: str,
    body: Mapping[str, Any],
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> dict[str, Any]:
    scenario = scenario_from_body(body, limits=limits)
    axis = body.get("axis")
    if axis is None:
        return {"section": section, "state": _state_for(section, scenario)}
    if not isinstance(axis, Mapping):
        raise ApiValidationError([{"loc": "axis", "msg": "axis must be an object"}])
    try:
        _require_known_fields(axis, {"target", "values"}, loc="axis")
        target = _registered_sweep_target(
            scenario,
            axis.get("target"),
            "characterization axis",
        )
        require_effective_target(
            scenario,
            target,
            purpose="characterization axis",
        )
        values = parse_axis_values(
            axis.get("values"),
            loc="axis.values",
            limits=limits,
        )
        values = _normalize_target_values(
            target,
            values,
            generated_from_range=isinstance(axis.get("values"), Mapping),
            loc="axis.values",
        )
        _validate_target_values(scenario, target, values, loc="axis.values")
        physical_rows = []
        rows = []
        for value in values:
            effective = set_target(scenario, target, value)
            physical_row = _state_for(section, effective)
            physical_rows.append(physical_row)
            row = dict(physical_row)
            row[target] = value
            rows.append(row)
        if (
            len(values) >= 2
            and any(value != values[0] for value in values[1:])
            and all(row == physical_rows[0] for row in physical_rows[1:])
        ):
            raise CapabilityError(
                [
                    CapabilityIssue(
                        code="TARGET_HAS_NO_CHARACTERIZATION_EFFECT",
                        loc="axis.target",
                        msg=(
                            f"Target {target!r} does not change the requested "
                            f"{section!r} characterization."
                        ),
                        severity="error",
                        value=target,
                        context={
                            "section": section,
                            "axis_points": len(values),
                        },
                        suggestion=(
                            "Choose an axis that changes this characterization "
                            "section, or request the section affected by the target."
                        ),
                    ),
                ],
            )
    except ApiValidationError:
        raise
    except (TypeError, ValueError) as exc:
        raise api_validation_error(exc, payload=body) from exc

    return {"section": section, "rows": rows}


def dynamics_preview(
    body: Mapping[str, Any],
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> dict[str, Any]:
    scenario = scenario_from_body(body, limits=limits)
    resolver = ParameterResolver()
    raw_points = body.get("time_points_s")
    if raw_points is None:
        raw_points = [0.0, scenario.duration_s / 2.0, scenario.duration_s]
    if not isinstance(raw_points, list | tuple):
        raise ApiValidationError(
            [{"loc": "time_points_s", "msg": "time_points_s must be a list"}],
        )
    if not raw_points:
        raise ApiValidationError(
            [
                {
                    "loc": "time_points_s",
                    "msg": "time_points_s must contain at least one item",
                },
            ],
        )
    if len(raw_points) > limits.max_time_points:
        issue = CapabilityIssue(
            code="TIME_POINT_LIMIT_EXCEEDED",
            loc="time_points_s",
            msg=(
                f"Dynamics preview requests {len(raw_points)} points; the limit is "
                f"{limits.max_time_points}."
            ),
            severity="error",
            value=len(raw_points),
            context={"max_time_points": limits.max_time_points},
            suggestion=(
                f"Reduce time_points_s to at most {limits.max_time_points} items."
            ),
        )
        raise ApiValidationError([issue.to_dict()])
    rows = []
    for index, time_s in enumerate(raw_points):
        if isinstance(time_s, bool) or not isinstance(time_s, int | float):
            raise ApiValidationError(
                [
                    {
                        "loc": f"time_points_s.{index}",
                        "msg": (
                            "time point must be a finite non-negative number, "
                            f"got {time_s!r}"
                        ),
                    },
                ],
            )
        time = float(time_s)
        if not math.isfinite(time) or time < 0.0:
            raise ApiValidationError(
                [
                    {
                        "loc": f"time_points_s.{index}",
                        "msg": (
                            "time point must be finite and non-negative, "
                            f"got {time_s!r}"
                        ),
                    },
                ],
            )
        row = {"time_s": time}
        try:
            row.update(resolver.parameter_values(scenario, time_s=time))
        except (TypeError, ValueError) as exc:
            raise api_validation_error(exc, payload=body) from exc
        rows.append(row)
    return {"rows": rows}


def inspect_scenario(
    body: Mapping[str, Any],
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> dict[str, Any]:
    """Resolve once and return the data needed by the scenario designer."""

    requested = scenario_from_body(body, limits=limits)
    effective = ParameterResolver().scenario_at(requested, time_s=0.0)
    estimate = estimate_run_cost(effective, limits=limits)
    warnings = [
        issue.to_dict()
        for issue in capability_issues(requested)
        if issue.severity == "warning"
    ]
    return {
        "valid": True,
        "digest": requested.digest(),
        "scenario": requested.to_dict(),
        "effective_digest": effective.digest(),
        "effective_scenario": effective.to_dict(),
        "resolution_time_s": 0.0,
        "warnings": warnings,
        "characterizations": {
            section: _state_for(section, effective)
            for section in ("source", "channel", "detector", "timing")
        },
        "cost_estimate": estimate.to_dict(),
    }


def import_experiment_payload(body: Mapping[str, Any]) -> dict[str, Any]:
    source = (
        body["experiment"]
        if "experiment" in body and isinstance(body["experiment"], Mapping)
        else body
    )
    payload = dict(source)
    payload["provenance"] = _unverified_import_provenance(
        payload.get("provenance", {})
    )
    if "last_result" in payload:
        payload["last_result"] = _mark_imported_result(payload["last_result"])
    for field in ("runs", "curves"):
        records = payload.get(field)
        if not isinstance(records, list):
            continue
        payload[field] = [
            _mark_imported_record(record) if isinstance(record, Mapping) else record
            for record in records
        ]
    return payload


def _mark_imported_record(value: Mapping[str, Any]) -> dict[str, Any]:
    record = dict(value)
    if "provenance" in record:
        record["provenance"] = _unverified_import_provenance(record["provenance"])
    if "result" in record:
        record["result"] = _mark_imported_result(record["result"])
    return record


def _mark_imported_result(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    result = dict(value)
    if "provenance" in result:
        result["provenance"] = _unverified_import_provenance(result["provenance"])
    return result


def _unverified_import_provenance(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    provenance = dict(value)
    # These boundary-owned fields override any claim inside the imported file.
    provenance["verification_status"] = "unverified_import"
    provenance["claims_verified"] = False
    return provenance


def presets_payload() -> dict[str, Any]:
    # Scientific definitions live in ``qiskit_qkd.config.domain_metadata``;
    # this compatibility envelope preserves the historical response shape.
    presets = builtin_presets()
    return {
        "presets": [
            {"name": name, "scenario": scenario.to_dict(), "digest": scenario.digest()}
            for name, scenario in presets
        ],
    }


def parse_axis_values(
    values: Any,
    *,
    loc: str = "values",
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> list[float | int | bool | None]:
    if isinstance(values, list):
        if not values:
            raise ApiValidationError(
                [{"loc": loc, "msg": "values must contain at least one item"}],
            )
        if len(values) > limits.max_axis_points:
            raise CapabilityError(
                [
                    CapabilityIssue(
                        code="AXIS_POINT_LIMIT_EXCEEDED",
                        loc=loc,
                        msg=(
                            f"Axis requests {len(values)} points; the limit is "
                            f"{limits.max_axis_points}."
                        ),
                        severity="error",
                        value=len(values),
                        context={"max_axis_points": limits.max_axis_points},
                        suggestion=(
                            "Reduce the list to at most "
                            f"{limits.max_axis_points} items."
                        ),
                    ),
                ],
            )
        return values
    if not isinstance(values, Mapping):
        raise ApiValidationError(
            [{"loc": loc, "msg": "values must be a list or range"}],
        )
    _require_known_fields(
        values,
        {"start", "stop", "steps", "scale"},
        loc=loc,
    )
    try:
        raw_start = values["start"]
        raw_stop = values["stop"]
        raw_steps = values["steps"]
    except KeyError as exc:
        raise ApiValidationError(
            [{"loc": f"{loc}.{exc.args[0]}", "msg": "range field is required"}],
        ) from exc
    if isinstance(raw_start, bool) or isinstance(raw_stop, bool):
        raise ApiValidationError(
            [{"loc": loc, "msg": "range bounds must be numeric, not boolean"}],
        )
    try:
        start = float(raw_start)
        stop = float(raw_stop)
    except (TypeError, ValueError) as exc:
        raise ApiValidationError(
            [{"loc": loc, "msg": f"range values must be numeric: {exc}"}],
        ) from exc
    if not math.isfinite(start) or not math.isfinite(stop):
        raise ApiValidationError(
            [{"loc": loc, "msg": "range bounds must be finite"}],
        )
    if not isinstance(raw_steps, int) or isinstance(raw_steps, bool) or raw_steps < 1:
        raise ApiValidationError(
            [
                {
                    "loc": f"{loc}.steps",
                    "msg": "steps must be a positive integer",
                },
            ],
        )
    steps = raw_steps
    if steps > limits.max_axis_points:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="AXIS_POINT_LIMIT_EXCEEDED",
                    loc=f"{loc}.steps",
                    msg=(
                        f"Range requests {steps} points; the per-axis limit is "
                        f"{limits.max_axis_points}."
                    ),
                    severity="error",
                    value=steps,
                    context={"max_axis_points": limits.max_axis_points},
                    suggestion=(f"Reduce steps to at most {limits.max_axis_points}."),
                ),
            ],
        )
    scale = values.get("scale", "linear")
    if scale not in {"linear", "log"}:
        raise ApiValidationError(
            [
                {
                    "loc": f"{loc}.scale",
                    "msg": "scale must be 'linear' or 'log'",
                },
            ],
        )
    if steps == 1:
        return [start]
    if scale == "log":
        if start <= 0.0 or stop <= 0.0:
            raise ApiValidationError(
                [{"loc": loc, "msg": "log ranges require positive bounds"}],
            )
        ratio = (math.log10(stop) - math.log10(start)) / (steps - 1)
        return [10 ** (math.log10(start) + index * ratio) for index in range(steps)]
    delta = (stop - start) / (steps - 1)
    return [start + index * delta for index in range(steps)]


def _require_known_fields(
    value: Mapping[str, Any],
    allowed: set[str],
    *,
    loc: str,
) -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if not unknown:
        return
    raise CapabilityError(
        [
            CapabilityIssue(
                code="UNKNOWN_REQUEST_FIELD",
                loc=f"{loc}.{field}",
                msg=f"Field {field!r} is not supported in {loc}.",
                severity="error",
                value=field,
                context={"allowed_fields": sorted(allowed)},
                suggestion=f"Remove {field!r} or use one of the allowed fields.",
            )
            for field in unknown
        ],
    )


def _require_sweep_size(
    axis_values: list[float | int | bool | None],
    series_values: list[float | int | bool | None] | None,
    repeats: int,
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> None:
    series_points = len(series_values) if series_values is not None else 1
    total = len(axis_values) * series_points * repeats
    if total <= limits.max_sweep_evaluations:
        return
    raise CapabilityError(
        [
            CapabilityIssue(
                code="SWEEP_SIZE_EXCEEDED",
                loc="sweep",
                msg=(
                    f"Sweep requests {total} evaluations; the limit is "
                    f"{limits.max_sweep_evaluations}."
                ),
                severity="error",
                value=total,
                context={
                    "axis_points": len(axis_values),
                    "series_points": series_points,
                    "repeats": repeats,
                    "max_evaluations": limits.max_sweep_evaluations,
                },
                suggestion=(
                    "Reduce axis points, series points, or repeats so their "
                    f"product is at most {limits.max_sweep_evaluations}."
                ),
            ),
        ],
    )


def set_target(scenario: Scenario, target: str, value: Any) -> Scenario:
    section, field = validate_parameter_target(target).split(".")
    if section == "scenario":
        return replace(scenario, **{field: value})
    section_config = getattr(scenario, section)
    return replace(scenario, **{section: replace(section_config, **{field: value})})


def _registered_sweep_target(
    scenario: Scenario,
    target: Any,
    purpose: str,
) -> str:
    raw_target = "" if target is None else str(target)
    try:
        return validate_parameter_target(raw_target)
    except (TypeError, ValueError):
        return require_effective_target(scenario, raw_target, purpose=purpose)


def _validate_target_values(
    scenario: Scenario,
    target: str,
    values: list[float | int | bool | None],
    *,
    loc: str,
) -> None:
    for index, value in enumerate(values):
        try:
            set_target(scenario, target, value)
        except (TypeError, ValueError) as exc:
            raise CapabilityError(
                [
                    CapabilityIssue(
                        code="TARGET_VALUE_INVALID",
                        loc=f"{loc}.{index}",
                        msg=f"Value {value!r} is invalid for target {target!r}: {exc}",
                        severity="error",
                        value=value,
                        context={"target": target, "index": index},
                        suggestion="Use values within the target's catalog limits.",
                    ),
                ],
            ) from exc


def _normalize_target_values(
    target: str,
    values: list[float | int | bool | None],
    *,
    generated_from_range: bool,
    loc: str,
) -> list[float | int | bool | None]:
    if target != "scenario.pulses":
        return values

    normalized: list[float | int | bool | None] = []
    for index, value in enumerate(values):
        valid_value = (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            if generated_from_range
            else isinstance(value, int) and not isinstance(value, bool)
        )
        if not valid_value:
            raise CapabilityError(
                [
                    CapabilityIssue(
                        code="TARGET_VALUE_REQUIRES_INTEGER",
                        loc=f"{loc}.{index}",
                        msg=(
                            f"Target {target!r} requires integer values, got {value!r}."
                        ),
                        severity="error",
                        value=value,
                        context={"target": target, "index": index},
                        suggestion=(
                            "Use integers, or a range that can be rounded to "
                            "integer pulse counts."
                        ),
                    ),
                ],
            )
        normalized.append(int(round(float(value))))
    duplicates: list[int] = []
    seen: set[int] = set()
    for value in normalized:
        assert isinstance(value, int)
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TARGET_VALUES_COLLIDE",
                    loc=loc,
                    msg=(
                        f"Values for {target!r} collapse to duplicate integer "
                        f"pulse counts after normalization: {duplicates!r}."
                    ),
                    severity="error",
                    value=list(normalized),
                    context={"target": target, "duplicate_values": duplicates},
                    suggestion=(
                        "Use distinct integer pulse counts or reduce the number "
                        "of range steps."
                    ),
                ),
            ],
        )
    return normalized


def _annotate_sweep_rows(
    rows: list[dict[str, Any]],
    *,
    requested_scenario_digest: str,
    resolution_time_s: float | None = None,
) -> None:
    for row in rows:
        row["requested_scenario_digest"] = requested_scenario_digest
        resolved_at = row.get("resolution_time_s", resolution_time_s)
        if resolved_at is not None:
            row["resolution_time_s"] = float(resolved_at)
        effective_digest = row.get("effective_scenario_digest")
        if not isinstance(effective_digest, str):
            continue
        raw_provenance = row.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, Mapping) else {}
        _annotate_provenance(
            provenance,
            requested_scenario_digest=requested_scenario_digest,
            effective_scenario_digest=effective_digest,
            resolution_time_s=(float(resolved_at) if resolved_at is not None else None),
        )
        row["provenance"] = provenance


def _annotate_provenance(
    provenance: dict[str, Any],
    *,
    requested_scenario_digest: str,
    effective_scenario_digest: str,
    resolution_time_s: float | None,
) -> None:
    provenance["requested_scenario_digest"] = requested_scenario_digest
    provenance["effective_scenario_digest"] = effective_scenario_digest
    if resolution_time_s is not None:
        provenance["resolution_time_s"] = resolution_time_s


def _annotate_payload_provenance(
    payload: dict[str, Any],
    *,
    requested_scenario_digest: str,
    effective_scenario_digest: str,
    resolution_time_s: float | None,
) -> None:
    raw_provenance = payload.get("provenance")
    provenance = (
        normalize_json_object(raw_provenance, path="provenance")
        if isinstance(raw_provenance, Mapping)
        else {}
    )
    _annotate_provenance(
        provenance,
        requested_scenario_digest=requested_scenario_digest,
        effective_scenario_digest=effective_scenario_digest,
        resolution_time_s=resolution_time_s,
    )
    payload["provenance"] = provenance


def _state_for(section: str, scenario: Scenario) -> dict[str, Any]:
    if section == "source":
        return source_state_from_scenario(scenario).to_dict()
    if section == "channel":
        return channel_state_from_scenario(scenario).to_dict()
    if section == "detector":
        return detector_state_from_scenario(scenario).to_dict()
    if section == "timing":
        return timing_state_from_scenario(scenario).to_dict()
    raise ApiValidationError(
        [{"loc": "section", "msg": f"unknown section {section!r}"}],
    )


def _protocol_for(scenario: Scenario) -> BB84Protocol | E91Protocol:
    if scenario.protocol.name == "e91":
        return E91Protocol()
    return BB84Protocol()


class _ProgressReportingProtocol:
    def __init__(
        self,
        protocol: BB84Protocol | E91Protocol,
        job_control: JobControl,
    ) -> None:
        self._protocol = protocol
        self._job_control = job_control

    def run(self, scenario: Scenario, backend: Any | None = None) -> Any:
        self._job_control.checkpoint()
        result = self._protocol.run(
            scenario,
            backend=backend,
            cancellation_check=self._job_control.checkpoint,
        )
        self._job_control.advance()
        return result


def _cap_event_sample(
    scenario: Scenario,
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> Scenario:
    if (
        scenario.store_full_event_log
        or scenario.event_sample_size <= limits.max_event_sample_size
    ):
        return scenario
    return replace(scenario, event_sample_size=limits.max_event_sample_size)


def _result_payload(result: dict[str, Any]) -> dict[str, Any]:
    # Non-full samples are bounded before execution by ``_cap_event_sample``.
    # When a caller explicitly requests the full event log, truncating it here
    # would contradict both ``store_full_event_log`` and ``aggregated=False``.
    return normalize_json_object(result, path="result")
