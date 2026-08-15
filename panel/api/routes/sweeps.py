from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from panel.api.costs import CostEstimate, estimate_sweep_cost
from panel.api.errors import ApiValidationError, api_validation_error
from panel.api.models import (
    CancellationResponse,
    CompactSweepResultResponse,
    JobStatusResponse,
    SweepCostEstimateResponse,
    SweepCreatedResponse,
    SweepRequest,
)
from panel.api.runtime import (
    scenario_from_body,
    sweep_scenario_job,
    validate_sweep_request,
)
from qiskit_qkd.config import Scenario

router = APIRouter(prefix="/api/sweeps", tags=["sweeps"])


@router.post("/estimate", response_model=SweepCostEstimateResponse)
def estimate_sweep(body: SweepRequest, request: Request) -> dict[str, object]:
    (
        _scenario,
        _axis,
        _series,
        _repeats,
        _axis_values,
        _series_values,
        estimate,
    ) = _preflight_sweep(body.as_payload(), request)
    return estimate.to_dict()


@router.post("", response_model=SweepCreatedResponse)
def create_sweep(body: SweepRequest, request: Request) -> dict[str, object]:
    payload = body.as_payload()
    (
        scenario,
        axis,
        series,
        repeats,
        axis_values,
        series_values,
        estimate,
    ) = _preflight_sweep(payload, request)
    limits = request.app.state.operational_limits
    total = len(axis_values) * repeats
    if series_values is not None:
        total *= len(series_values)
    record = request.app.state.job_manager.submit(
        "sweep",
        sweep_scenario_job,
        scenario.to_dict(),
        axis,
        series,
        repeats,
        limits,
        total=total,
        digest=scenario.digest(),
        cost=float(estimate.total_pulse_events),
        estimated_bytes=max(
            1024,
            int(estimate.estimated_artifact_bytes or 0),
        ),
    )
    return {
        "job_id": record.job_id,
        "status": record.status,
        "cost_estimate": estimate.to_dict(),
    }


def _preflight_sweep(
    payload: dict[str, Any],
    request: Request,
) -> tuple[
    Scenario,
    Mapping[str, Any],
    Mapping[str, Any] | None,
    int,
    list[float | int | bool | None],
    list[float | int | bool | None] | None,
    CostEstimate,
]:
    limits = request.app.state.operational_limits
    scenario = scenario_from_body(payload, limits=limits)
    axis = payload.get("axis")
    if not isinstance(axis, Mapping):
        raise ApiValidationError([{"loc": "axis", "msg": "axis must be an object"}])
    series = payload.get("series")
    if series is not None and not isinstance(series, Mapping):
        raise ApiValidationError(
            [{"loc": "series", "msg": "series must be an object or null"}],
        )
    try:
        repeats = payload.get("repeats", 1)
        axis_values, series_values = validate_sweep_request(
            scenario,
            axis,
            series,
            repeats,
            limits=limits,
        )
    except (TypeError, ValueError) as exc:
        raise api_validation_error(exc, payload=payload) from exc
    estimate = estimate_sweep_cost(
        scenario,
        axis,
        series,
        repeats,
        axis_values,
        series_values,
        limits=limits,
    )
    return scenario, axis, series, repeats, axis_values, series_values, estimate


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    response_model_exclude_none=True,
)
def get_sweep(job_id: str, request: Request) -> dict[str, object]:
    record = request.app.state.job_manager.get(job_id, kind="sweep")
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = record.to_status()
    # Polling is metadata-only for every size. Loading an artifact merely to
    # decide whether it is small would defeat lazy persistence.
    payload.pop("result", None)
    return payload


@router.get("/{job_id}/result", response_model=CompactSweepResultResponse)
def get_sweep_result(job_id: str, request: Request) -> dict[str, object]:
    """Load a completed sweep DTO on demand, never through status polling."""

    record = request.app.state.job_manager.get(job_id, kind="sweep")
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    if record.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"job result is not available while status is {record.status!r}",
        )
    result = record.get_result()
    if isinstance(result, dict):
        return result
    raise HTTPException(status_code=410, detail="job result is unavailable")


@router.delete(
    "/{job_id}",
    response_model=CancellationResponse,
    response_model_exclude_none=True,
)
def cancel_sweep(job_id: str, request: Request) -> dict[str, object]:
    manager = request.app.state.job_manager
    cancelled = manager.cancel(job_id, kind="sweep")
    record = manager.get(job_id, kind="sweep")
    if record is None:
        return {"cancelled": cancelled}
    return {
        "cancelled": cancelled,
        "cancellation_requested": record.status == "cancellation_requested",
        "status": record.status,
    }
