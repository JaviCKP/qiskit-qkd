from __future__ import annotations

from fastapi import APIRouter, Request

from panel.api.catalog import catalog_payload
from panel.api.models import (
    CatalogResponse,
    ScenarioInspectionResponse,
    ScenarioInspectRequest,
    ScenarioValidationResponse,
)
from panel.api.runtime import inspect_scenario, scenario_from_body
from qiskit_qkd.config import capability_issues

router = APIRouter(prefix="/api", tags=["scenarios"])


@router.get("/catalog", response_model=CatalogResponse)
def catalog() -> dict[str, object]:
    return catalog_payload()


@router.post("/scenarios/validate", response_model=ScenarioValidationResponse)
def validate_scenario(
    body: ScenarioInspectRequest,
    request: Request,
) -> dict[str, object]:
    scenario = scenario_from_body(
        body.as_payload(),
        limits=request.app.state.operational_limits,
    )
    warnings = [
        issue.to_dict()
        for issue in capability_issues(scenario)
        if issue.severity == "warning"
    ]
    return {
        "valid": True,
        "digest": scenario.digest(),
        "scenario": scenario.to_dict(),
        "warnings": warnings,
    }


@router.post("/scenarios/inspect", response_model=ScenarioInspectionResponse)
def inspect(body: ScenarioInspectRequest, request: Request) -> dict[str, object]:
    return inspect_scenario(
        body.as_payload(),
        limits=request.app.state.operational_limits,
    )
