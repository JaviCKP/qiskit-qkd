from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from panel.api.models import (
    DeletionResponse,
    ExperimentCreateRequest,
    ExperimentEnvelopeResponse,
    ExperimentImportRequest,
    ExperimentListResponse,
    ExperimentUpdateRequest,
)
from panel.api.runtime import import_experiment_payload, scenario_from_body

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


@router.get(
    "",
    response_model=ExperimentListResponse,
    response_model_exclude_none=True,
)
def list_experiments(
    request: Request,
    limit: int | None = Query(
        default=None,
        ge=1,
        le=1_000,
        description="Maximum number of experiment summaries to return (default 50).",
    ),
    offset: int | None = Query(
        default=None,
        ge=0,
        description="Number of valid experiment summaries to skip.",
    ),
) -> dict[str, object]:
    effective_limit = 50 if limit is None else limit
    effective_offset = 0 if offset is None else offset
    experiments, total = request.app.state.store.list_summaries(
        limit=effective_limit,
        offset=effective_offset,
    )
    response: dict[str, object] = {"experiments": experiments}
    # Keep the historical no-query envelope byte-compatible.  Once a caller
    # opts into pagination, expose deterministic metadata in the same envelope.
    if limit is not None or offset is not None:
        response["pagination"] = {
            "offset": effective_offset,
            "limit": effective_limit,
            "total": total,
            "has_more": effective_offset + len(experiments) < total,
        }
    return response


@router.post("", response_model=ExperimentEnvelopeResponse)
def create_experiment(
    body: ExperimentCreateRequest,
    request: Request,
) -> dict[str, object]:
    payload = body.as_payload()
    experiment = _save_experiment_payload(payload, request)
    return {"experiment": experiment}


@router.put("/{experiment_id}", response_model=ExperimentEnvelopeResponse)
def replace_experiment(
    experiment_id: str,
    body: ExperimentCreateRequest,
    request: Request,
) -> dict[str, object]:
    if request.app.state.store.get(experiment_id) is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    experiment = _save_experiment_payload(
        body.as_payload(),
        request,
        experiment_id=experiment_id,
    )
    return {"experiment": experiment}


def _save_experiment_payload(
    payload: dict[str, object],
    request: Request,
    *,
    experiment_id: str | None = None,
) -> dict[str, object]:
    scenario = scenario_from_body(
        payload,
        limits=request.app.state.operational_limits,
    )
    experiment = request.app.state.store.save(
        {
            **({"id": experiment_id} if experiment_id is not None else {}),
            "name": payload.get("name", "Experimento sin titulo"),
            "schema_version": payload.get("schema_version", 2),
            "scenario": scenario.to_dict(),
            "digest": scenario.digest(),
            "tags": payload.get("tags", []),
            "last_result": payload.get("last_result"),
            "curve_recipes": payload.get("curve_recipes", []),
            "runs": payload.get("runs", []),
            "curves": payload.get("curves", []),
            "provenance": payload.get("provenance", {}),
        },
    )
    return experiment


@router.post("/import", response_model=ExperimentEnvelopeResponse)
def import_experiment(
    body: ExperimentImportRequest,
    request: Request,
) -> dict[str, object]:
    experiment = request.app.state.store.save(
        import_experiment_payload(body.as_payload()),
    )
    return {"experiment": experiment}


@router.get("/{experiment_id}", response_model=ExperimentEnvelopeResponse)
def get_experiment(experiment_id: str, request: Request) -> dict[str, object]:
    experiment = request.app.state.store.get(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"experiment": experiment}


@router.patch("/{experiment_id}", response_model=ExperimentEnvelopeResponse)
def update_experiment(
    experiment_id: str,
    body: ExperimentUpdateRequest,
    request: Request,
) -> dict[str, object]:
    experiment = request.app.state.store.get(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    updated = request.app.state.store.save({**experiment, "name": body.name})
    return {"experiment": updated}


@router.get(
    "/{experiment_id}/export",
    response_model=ExperimentEnvelopeResponse,
)
def export_experiment(experiment_id: str, request: Request) -> dict[str, object]:
    experiment = request.app.state.store.get(experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return {"experiment": experiment}


@router.delete("/{experiment_id}", response_model=DeletionResponse)
def delete_experiment(experiment_id: str, request: Request) -> dict[str, bool]:
    return {"deleted": request.app.state.store.delete(experiment_id)}
