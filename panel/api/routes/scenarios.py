from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from panel.api.catalog import catalog_payload
from panel.api.runtime import scenario_from_body

router = APIRouter(prefix="/api", tags=["scenarios"])


@router.get("/catalog")
def catalog() -> dict[str, object]:
    return catalog_payload()


@router.post("/scenarios/validate")
def validate_scenario(body: dict[str, Any]) -> dict[str, Any]:
    scenario = scenario_from_body(body)
    return {"valid": True, "digest": scenario.digest(), "scenario": scenario.to_dict()}
