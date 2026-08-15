from __future__ import annotations

from fastapi import APIRouter, Request

from panel.api.models import ScenarioRequest
from panel.api.runtime import characterize_section

router = APIRouter(prefix="/api/characterize", tags=["characterize"])


@router.post("/{section}")
def characterize(
    section: str,
    body: ScenarioRequest,
    request: Request,
) -> dict[str, object]:
    return characterize_section(
        section,
        body.as_payload(),
        limits=request.app.state.operational_limits,
    )
