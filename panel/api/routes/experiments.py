from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from panel.api.runtime import import_experiment_payload, scenario_from_body

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get("")
def list_experiments(request: Request) -> dict[str, Any]:
    return {"experiments": request.app.state.store.list()}


@router.post("")
def create_experiment(body: dict[str, Any], request: Request) -> dict[str, Any]:
    scenario = scenario_from_body(body)
    experiment = request.app.state.store.save(
        {
            "name": body.get("name", "Experimento sin titulo"),
            "scenario": scenario.to_dict(),
            "digest": scenario.digest(),
            "tags": body.get("tags", []),
            "last_result": body.get("last_result"),
            "curve_recipes": body.get("curve_recipes", []),
        },
    )
    return {"experiment": experiment}


@router.post("/import")
def import_experiment(body: dict[str, Any], request: Request) -> dict[str, Any]:
    experiment = request.app.state.store.save(import_experiment_payload(body))
    return {"experiment": experiment}


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str, request: Request) -> dict[str, Any]:
    experiment = request.app.state.store.get(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"experiment": experiment}


@router.get("/{experiment_id}/export")
def export_experiment(experiment_id: str, request: Request) -> dict[str, Any]:
    experiment = request.app.state.store.get(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"experiment": experiment}


@router.delete("/{experiment_id}")
def delete_experiment(experiment_id: str, request: Request) -> dict[str, bool]:
    return {"deleted": request.app.state.store.delete(experiment_id)}
