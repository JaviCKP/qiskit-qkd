from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from panel.api.runtime import dynamics_preview

router = APIRouter(prefix="/api/dynamics", tags=["dynamics"])


@router.post("/preview")
def preview(body: dict[str, Any]) -> dict[str, Any]:
    return dynamics_preview(body)
