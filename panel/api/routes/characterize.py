from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from panel.api.runtime import characterize_section

router = APIRouter(prefix="/api/characterize", tags=["characterize"])


@router.post("/{section}")
def characterize(section: str, body: dict[str, Any]) -> dict[str, Any]:
    return characterize_section(section, body)
