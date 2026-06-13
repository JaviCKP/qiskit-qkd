from __future__ import annotations

from fastapi import APIRouter

from panel.api.runtime import presets_payload

router = APIRouter(prefix="/api", tags=["presets"])


@router.get("/presets")
def presets() -> dict[str, object]:
    return presets_payload()
