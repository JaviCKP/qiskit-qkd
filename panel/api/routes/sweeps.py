from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from panel.api.runtime import parse_axis_values, scenario_from_body, sweep_scenario_job

router = APIRouter(prefix="/api/sweeps", tags=["sweeps"])


@router.post("")
def create_sweep(body: dict[str, Any], request: Request) -> dict[str, Any]:
    scenario = scenario_from_body(body)
    axis = body["axis"]
    series = body.get("series")
    repeats = int(body.get("repeats", 1))
    total = len(parse_axis_values(axis["values"])) * max(repeats, 1)
    if series is not None:
        total *= len(parse_axis_values(series["values"]))
    record = request.app.state.job_manager.submit(
        "sweep",
        sweep_scenario_job,
        scenario.to_dict(),
        axis,
        series,
        repeats,
        total=total,
    )
    return {"job_id": record.job_id, "status": record.status}


@router.get("/{job_id}")
def get_sweep(job_id: str, request: Request) -> dict[str, Any]:
    record = request.app.state.job_manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    return record.to_status()


@router.delete("/{job_id}")
def cancel_sweep(job_id: str, request: Request) -> dict[str, bool]:
    return {"cancelled": request.app.state.job_manager.cancel(job_id)}
