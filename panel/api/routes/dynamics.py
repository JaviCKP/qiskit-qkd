from __future__ import annotations

from fastapi import APIRouter, Request

from panel.api.models import ScenarioRequest
from panel.api.runtime import dynamics_preview

router = APIRouter(prefix="/api/dynamics", tags=["dynamics"])


@router.post("/preview")
def preview(body: ScenarioRequest, request: Request) -> dict[str, object]:
    return dynamics_preview(
        body.as_payload(),
        limits=request.app.state.operational_limits,
    )
