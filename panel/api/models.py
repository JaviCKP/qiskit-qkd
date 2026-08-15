"""Typed FastAPI boundary models with compatibility for legacy extra fields."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictBool,
    StrictInt,
    StrictStr,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)


class StrictContractModel(BaseModel):
    """Response models whose fields are part of the versioned wire contract."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ScenarioInput(ApiModel):
    """Typed scenario envelope; domain dataclasses remain the source of truth."""

    schema_version: StrictInt | None = None
    pulses: StrictInt | None = None
    clock_rate_hz: FiniteFloat | None = None
    seed: StrictInt | None = None
    protocol: Any | None = None
    source: Any | None = None
    channel: Any | None = None
    detector: Any | None = None
    timing: Any | None = None
    post_processing: Any | None = None
    eavesdropper: Any | None = None
    e91: Any | None = None
    dynamic: Any | None = None
    event_sample_size: StrictInt | None = None
    store_full_event_log: StrictBool | None = None
    metadata: Any | None = None


class ScenarioRequest(ApiModel):
    """Common request shape; extra fields keep bare-scenario compatibility."""

    scenario: ScenarioInput | None = None

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class RunRequest(ScenarioRequest):
    label: str | None = None


class AxisInput(ApiModel):
    target: str | None = None
    values: Any | None = None
    time_axis: Any | None = None


class SweepRequest(ScenarioRequest):
    axis: AxisInput | None = None
    series: AxisInput | None = None
    repeats: Any = 1


class ScenarioInspectRequest(ScenarioRequest):
    pass


class CatalogFieldMetadata(ApiModel):
    """Additive scientific metadata carried alongside legacy catalog fields."""

    key: str
    default: Any | None = None
    unit: str | None = None
    options: list[str] | None = None
    visible_when: dict[str, Any] | None = None
    conditions: dict[str, Any] | None = None
    dependencies: list[str] = Field(default_factory=list)
    applicable_protocols: list[str] = Field(default_factory=list)
    applicable_source_kinds: list[str] = Field(default_factory=list)
    applicable_channel_kinds: list[str] = Field(default_factory=list)
    applicable_detector_kinds: list[str] = Field(default_factory=list)


class CatalogResponse(ApiModel):
    """Versioned catalog envelope; legacy keys remain permissive/additive."""

    metadata_version: StrictInt | None = None
    default_medium_id: str | None = None
    default_scenario: dict[str, Any] | None = None
    field_defaults: dict[str, Any] = Field(default_factory=dict)
    fields: list[CatalogFieldMetadata] = Field(default_factory=list)
    media: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class PresetResponse(ApiModel):
    name: str
    digest: str
    scenario: dict[str, Any]


class PresetsResponse(ApiModel):
    presets: list[PresetResponse] = Field(default_factory=list)


class CostEstimateResponse(ApiModel):
    estimate_kind: Literal["upper_bound"]
    evaluations: StrictInt
    pulses_per_evaluation: StrictInt
    total_pulse_events: StrictInt
    estimated_max_circuits: StrictInt
    shots_per_circuit: StrictInt
    estimated_max_shots: StrictInt
    estimated_stored_events: StrictInt
    backend: Literal["statevector", "aer", "mixed"]
    full_event_log: StrictBool
    warnings: list[str]


class SweepCostEstimateResponse(CostEstimateResponse):
    """Sweep estimate adds compact payload/artifact admission bounds."""

    estimated_payload_bytes: StrictInt
    estimated_artifact_bytes: StrictInt
    estimated_total_bytes: StrictInt


JobStatusValue = Literal[
    "queued",
    "running",
    "cancellation_requested",
    "cancelled",
    "timed_out",
    "done",
    "error",
    "interrupted",
    "expired",
]


class RunCreatedResponse(ApiModel):
    job_id: str
    status: JobStatusValue
    digest: str
    cost_estimate: CostEstimateResponse


class SweepCreatedResponse(ApiModel):
    job_id: str
    status: JobStatusValue
    cost_estimate: SweepCostEstimateResponse


SweepScalar = StrictBool | StrictInt | FiniteFloat | StrictStr | None


class CompactSweepSummaryResponse(StrictContractModel):
    schema_version: Literal[2]
    row_count: StrictInt
    columns: dict[str, list[SweepScalar]]
    missing: dict[str, list[StrictInt]] = Field(default_factory=dict)


class CompactSweepResultResponse(StrictContractModel):
    """Versioned, metadata-factorized sweep artifact returned on demand."""

    schema_version: Literal[2]
    row_encoding: Literal["scalar-records-v1"]
    row_count: StrictInt
    requested_scenario_digest: str
    provenance: dict[str, Any]
    assessment: dict[str, Any]
    effective_model: dict[str, Any]
    row_invariants: dict[str, SweepScalar]
    rows: list[dict[str, SweepScalar]]
    provenance_columns: dict[str, Any] = Field(default_factory=dict)
    provenance_missing: dict[str, list[StrictInt]] = Field(default_factory=dict)
    assessment_columns: dict[str, Any] = Field(default_factory=dict)
    assessment_missing: dict[str, list[StrictInt]] = Field(default_factory=dict)
    effective_model_columns: dict[str, Any] = Field(default_factory=dict)
    effective_model_missing: dict[str, list[StrictInt]] = Field(default_factory=dict)
    summary: CompactSweepSummaryResponse


class JobProgressResponse(ApiModel):
    done: StrictInt
    total: StrictInt


class JobTimestampsResponse(ApiModel):
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    expires_at: str | None = None
    expired_at: str | None = None
    updated_at: str


class JobArtifactResponse(ApiModel):
    digest: str | None = None
    size_bytes: StrictInt


class JobStatusResponse(ApiModel):
    job_id: str
    kind: str
    status: JobStatusValue
    progress: JobProgressResponse
    elapsed_s: FiniteFloat
    timestamps: JobTimestampsResponse
    timed_out: StrictBool | None = None
    error: str | None = None
    error_code: str | None = None
    issues: list[dict[str, Any]] | None = None
    artifact: JobArtifactResponse | None = None
    result: dict[str, Any] | None = None
    result_summary: dict[str, Any] | None = None


class CancellationResponse(ApiModel):
    cancelled: StrictBool
    cancellation_requested: StrictBool | None = None
    status: JobStatusValue | None = None


class ScenarioValidationResponse(ApiModel):
    valid: StrictBool
    digest: str
    scenario: dict[str, Any]
    warnings: list[dict[str, Any]]


class ScenarioInspectionResponse(ScenarioValidationResponse):
    effective_digest: str
    effective_scenario: dict[str, Any]
    resolution_time_s: FiniteFloat
    characterizations: dict[str, dict[str, Any]]
    cost_estimate: CostEstimateResponse


class ExperimentCreateRequest(ScenarioRequest):
    name: str = "Experimento sin titulo"
    tags: list[StrictStr] = Field(default_factory=list)
    schema_version: StrictInt = 2
    last_result: ExperimentResult | None = None
    curve_recipes: list[dict[str, Any]] = Field(default_factory=list)
    runs: list[ExperimentRun] = Field(default_factory=list)
    curves: list[ExperimentCurve] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ExperimentUpdateRequest(ApiModel):
    name: str


class ExperimentImportRequest(ApiModel):
    experiment: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class ExperimentResponse(ApiModel):
    id: str
    origin: Literal["user"]
    name: str
    schema_version: StrictInt = 2
    digest: str
    scenario: dict[str, Any]
    tags: list[StrictStr]
    created_at: str
    updated_at: str
    last_result: ExperimentResult | None = None
    curve_recipes: list[dict[str, Any]] = Field(default_factory=list)
    runs: list[ExperimentRun] = Field(default_factory=list)
    curves: list[ExperimentCurve] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ExperimentEnvelopeResponse(ApiModel):
    experiment: ExperimentResponse


class ExperimentListResponse(ApiModel):
    """Backward-compatible envelope containing lightweight summaries."""

    experiments: list[ExperimentSummary]
    pagination: ExperimentPagination | None = None


class ExperimentRun(ApiModel):
    """Common run DTO; extra fields preserve producer-specific evidence."""

    job_id: str | None = None
    jobId: str | None = None
    run_id: str | None = None
    id: str | None = None
    digest: str | None = None
    result: dict[str, Any] | None = None


class ExperimentCurve(ApiModel):
    """Common curve DTO; metric/axis details remain producer-extensible."""

    job_id: str | None = None
    jobId: str | None = None
    curve_id: str | None = None
    id: str | None = None
    metric: str | None = None
    result: dict[str, Any] | None = None


class ExperimentResult(ApiModel):
    """Result summary DTO with typed evidence sections."""

    metrics: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    classical: dict[str, Any] | None = None
    qiskit: dict[str, Any] | None = None
    decoy: dict[str, Any] | None = None
    bell: dict[str, Any] | None = None
    event_sample: list[dict[str, Any]] | None = None


class ExperimentSummary(StrictContractModel):
    """List representation that intentionally omits scenario/results/logs."""

    id: str
    origin: Literal["user"]
    name: str
    schema_version: StrictInt
    digest: str
    tags: list[StrictStr]
    created_at: str
    updated_at: str
    runs_count: StrictInt = 0
    curves_count: StrictInt = 0


class ExperimentPagination(ApiModel):
    offset: StrictInt
    limit: StrictInt
    total: StrictInt
    has_more: StrictBool


class DeletionResponse(ApiModel):
    deleted: StrictBool


ExperimentListResponse.model_rebuild()
ExperimentCreateRequest.model_rebuild()
ExperimentResponse.model_rebuild()
