from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from panel.api.costs import estimate_run_cost
from panel.api.models import (
    CancellationResponse,
    CostEstimateResponse,
    JobStatusResponse,
    RunCreatedResponse,
    RunRequest,
)
from panel.api.runtime import run_scenario_job, scenario_from_body
from qiskit_qkd.temporal import ParameterResolver

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("/estimate", response_model=CostEstimateResponse)
def estimate_run(body: RunRequest, request: Request) -> dict[str, object]:
    limits = request.app.state.operational_limits
    scenario = scenario_from_body(body.as_payload(), limits=limits)
    effective = ParameterResolver().scenario_at(scenario, time_s=0.0)
    return estimate_run_cost(effective, limits=limits).to_dict()


@router.post("", response_model=RunCreatedResponse)
def create_run(body: RunRequest, request: Request) -> dict[str, object]:
    payload = body.as_payload()
    limits = request.app.state.operational_limits
    scenario = scenario_from_body(payload, limits=limits)
    effective = ParameterResolver().scenario_at(scenario, time_s=0.0)
    estimate = estimate_run_cost(effective, limits=limits)
    record = request.app.state.job_manager.submit(
        "run",
        run_scenario_job,
        scenario.to_dict(),
        limits,
        total=1,
        digest=scenario.digest(),
        cost=float(estimate.total_pulse_events),
        estimated_bytes=max(1024, int(estimate.estimated_stored_events) * 256),
    )
    return {
        "job_id": record.job_id,
        "status": record.status,
        "digest": scenario.digest(),
        "cost_estimate": estimate.to_dict(),
    }


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    response_model_exclude_none=True,
)
def get_run(job_id: str, request: Request) -> dict[str, object]:
    record = request.app.state.job_manager.get(job_id, kind="run")
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = record.to_status()
    # Status polling must stay metadata-only.  In particular, do not load a
    # multi-megabyte result artifact merely to expose its persisted summary.
    payload.pop("result", None)
    return payload


@router.get("/{job_id}/result")
def get_run_result(job_id: str, request: Request) -> dict[str, Any]:
    record = request.app.state.job_manager.get(job_id, kind="run")
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = record.to_status()
    if record.status == "done":
        result = record.get_result()
        if isinstance(result, dict) and isinstance(result.get("result"), dict):
            return result["result"]
        raise HTTPException(
            status_code=410,
            detail=(
                f"job result is unavailable; error_code="
                f"{record.error_code or 'RESULT_UNAVAILABLE'}"
            ),
        )
    raise HTTPException(
        status_code=409,
        detail=f"job result is not available while status is {payload['status']!r}",
    )


@router.delete(
    "/{job_id}",
    response_model=CancellationResponse,
    response_model_exclude_none=True,
)
def cancel_run(job_id: str, request: Request) -> dict[str, object]:
    manager = request.app.state.job_manager
    cancelled = manager.cancel(job_id, kind="run")
    record = manager.get(job_id, kind="run")
    if record is None:
        return {"cancelled": cancelled}
    return {
        "cancelled": cancelled,
        "cancellation_requested": record.status == "cancellation_requested",
        "status": record.status,
    }
