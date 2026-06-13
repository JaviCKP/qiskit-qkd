from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from panel.api.runtime import run_scenario_job, scenario_from_body

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("")
def create_run(body: dict[str, Any], request: Request) -> dict[str, Any]:
    scenario = scenario_from_body(body)
    record = request.app.state.job_manager.submit(
        "run",
        run_scenario_job,
        scenario.to_dict(),
        total=1,
    )
    return {
        "job_id": record.job_id,
        "status": record.status,
        "digest": scenario.digest(),
    }


@router.get("/{job_id}")
def get_run(job_id: str, request: Request) -> dict[str, Any]:
    record = request.app.state.job_manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = record.to_status()
    if record.status == "done":
        payload["result_summary"] = record.result["result_summary"]
        payload.pop("result", None)
    return payload


@router.get("/{job_id}/result")
def get_run_result(job_id: str, request: Request) -> dict[str, Any]:
    record = request.app.state.job_manager.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    payload = record.to_status()
    if record.status == "done":
        return record.result["result"]
    return payload


@router.delete("/{job_id}")
def cancel_run(job_id: str, request: Request) -> dict[str, bool]:
    return {"cancelled": request.app.state.job_manager.cancel(job_id)}
