import type { components } from './schema'
import { hydrateMediumScenarios } from '@/features/lab/mediums'

export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[]
export type JsonObject = { [key: string]: JsonValue }

export interface ProtocolPayload extends JsonObject {
  name: string
  basis_choices: string[]
}

export interface DecoyIntensityPayload extends JsonObject {
  name: string
  mean_photon_number: number
  selection_probability: number
}

export interface SourcePayload extends JsonObject {
  kind: string
  emission_probability: number
  mean_photon_number: number | null
  preparation_error_probability: number
  decoy_intensities: DecoyIntensityPayload[]
}

export interface ChannelPayload extends JsonObject {
  kind: string
  distance_km: number
  attenuation_db_km: number
  fixed_loss_db: number
  wavelength_nm: number
  transmitter_aperture_m: number
  receiver_aperture_m: number
  beam_divergence_rad: number
  atmospheric_extinction_db_km: number
  scintillation_sigma: number
  pointing_jitter_rad: number
  underwater_extinction_m_inv: number
  underwater_scattering_broadening_ns_per_m: number
  depolarizing_probability: number
  phase_damping_probability: number
  polarization_rotation_y_rad: number
  polarization_rotation_z_rad: number
  background_count_rate_hz: number
  pmd_coefficient_ps_sqrt_km: number
  chromatic_dispersion_ps_nm_km: number
  source_spectral_width_nm: number
  polarization_dependent_loss_db: number
  pdl_axis_basis: string
  pdl_axis_bit: number
  classical_channel_power_mw: number
  raman_coefficient_hz_mw_km: number
  raman_filter_isolation_db: number
}

export interface DetectorPayload extends JsonObject {
  kind: string
  efficiency: number
  dark_count_rate_hz: number
  gate_width_s: number
  dead_time_s: number
  afterpulse_probability: number
  readout_error_probability: number
  double_click_policy: string
}

export interface TimingPayload extends JsonObject {
  propagation_delay_s: number
  jitter_std_s: number
  clock_offset_s: number
  clock_drift_ppm: number
  slot_assignment_policy: string
}

export interface PostProcessingPayload extends JsonObject {
  sifting_enabled: boolean
  qber_abort_threshold: number | null
  qber_sample_fraction: number
  error_correction_efficiency: number
  reconciliation_block_size: number
  privacy_amplification_enabled: boolean
  decoy_security_estimation_enabled: boolean
  decoy_security_method: string
}

export interface EavesdropperPayload extends JsonObject {
  kind: string
  intercept_probability: number
  pns_split_probability: number
  pns_block_single_photon_probability: number
}

export interface E91Payload extends JsonObject {
  bell_state: string
  alice_angles_rad: number[]
  bob_angles_rad: number[]
  key_setting_pairs: number[][]
  chsh_terms: number[][]
  bob_key_bit_flip: boolean
  chsh_estimation_enabled: boolean
}

export interface DynamicPayload extends JsonObject {
  parameter_schedules: JsonObject[]
}

export type ScenarioPayload = components['schemas']['ScenarioInput'] & JsonObject & {
  schema_version: number
  pulses: number
  clock_rate_hz: number
  seed: number
  protocol: ProtocolPayload
  source: SourcePayload
  channel: ChannelPayload
  detector: DetectorPayload
  timing: TimingPayload
  post_processing: PostProcessingPayload
  eavesdropper: EavesdropperPayload
  e91: E91Payload
  dynamic: DynamicPayload
  event_sample_size: number
  store_full_event_log: boolean
  metadata: JsonObject
}

export type CatalogField = {
  key: string
  label_es: string
  type: string
  unit: string | null
  default: unknown
  min?: number | null
  max?: number | null
  step?: number | null
  scale?: 'linear' | 'log'
  options?: string[] | null
  visible_when?: { target: string; equals: unknown } | null
  sweepable: boolean
  dynamic?: boolean
  applicable_protocols?: string[]
  applicable_source_kinds?: string[]
  applicable_channel_kinds?: string[]
  applicable_detector_kinds?: string[]
  effect_status?: 'active' | 'ignored' | 'unsupported'
  effect_reason?: string
}

export type CatalogSection = {
  key: string
  label_es: string
  fields: CatalogField[]
}

export type MetricCapability = {
  key: string
  applicable_protocols?: string[]
  defined_when?: string
  scope?: string
}

export type CatalogMetric = {
  key: string
  label_es: string
  unit: string | null
  applicable_protocols?: string[]
  defined_when?: string
  scope?: string
}

export type CatalogCapabilities = {
  parameters?: Record<string, Omit<CatalogField, 'key' | 'label_es' | 'type' | 'unit' | 'default' | 'sweepable'>>
  metrics?: Record<string, MetricCapability>
  aliases?: Record<string, Record<string, string>>
}

type GeneratedCatalogMetadataField = components['schemas']['CatalogFieldMetadata']
export type CatalogMetadataField = GeneratedCatalogMetadataField & {
  key: string
  default: unknown
  unit: string | null
  options?: string[] | null
  visible_when?: { target: string; equals: unknown } | null
  conditions?: Record<string, unknown> | null
  dependencies?: string[]
  applicable_protocols?: string[]
  applicable_source_kinds?: string[]
  applicable_channel_kinds?: string[]
  applicable_detector_kinds?: string[]
}

export type CatalogMediumMetadata = {
  id: string
  channel_kinds: string[]
  scenario: ScenarioPayload
}

type GeneratedCatalog = components['schemas']['CatalogResponse']
export type Catalog = Omit<GeneratedCatalog, 'sections' | 'metrics' | 'capabilities' | 'metadata_version' | 'default_medium_id' | 'default_scenario' | 'field_defaults' | 'fields' | 'media'> & {
  sections: CatalogSection[]
  metrics: CatalogMetric[]
  capabilities?: CatalogCapabilities
  metadata_version?: number
  default_medium_id?: string
  default_scenario?: ScenarioPayload
  field_defaults?: Record<string, unknown>
  fields?: CatalogMetadataField[]
  media?: CatalogMediumMetadata[]
}

export const DOMAIN_METADATA_VERSION = 1

/** Explicit, versioned marker for the small offline/default bootstrap. */
export const OFFLINE_METADATA_VERSION = DOMAIN_METADATA_VERSION

export type ResultAssessment = {
  protocol?: string
  data_status?: 'available' | 'insufficient_data'
  qber_defined?: boolean
  qber_value?: number | null
  sample_size?: number
  qber_method?:
    | 'revealed_sample'
    | 'full_sifted_key_diagnostic'
    | 'unavailable'
  threshold?: number | null
  threshold_exceeded?: boolean | null
  threshold_decision_source?:
    | 'classical_estimate'
    | 'metrics_legacy'
    | 'disabled'
    | 'unavailable'
  verification_status?:
    | 'passed'
    | 'failed'
    | 'not_performed'
    | 'not_applicable'
    | 'unknown'
  key_status?:
    | 'estimated_key_available'
    | 'no_key_insufficient_data'
    | 'no_key_threshold_exceeded'
    | 'no_key_verification_failed'
    | 'no_extractable_key'
    | 'unknown'
  rate_estimate_status?: 'available' | 'unavailable' | 'inconsistent_with_key_status'
  rate_estimate_bps?: number | null
  rate_estimate_method?: string
  security_scope?: 'pedagogical_asymptotic_diagnostic' | string
  finite_key?: boolean
  composable?: boolean
  reason_codes?: string[]
  reasons?: string[]
  assumptions?: string[]
  observed_chsh_s?: number | null
  chsh_sample_size?: number
  chsh_sample_size_by_term?: { [term: string]: number }
  observed_threshold_exceeded?: boolean | null
  conclusion_scope?: 'diagnostic_fair_sampling_no_significance_test' | string
}

type GeneratedJobStatus = components['schemas']['JobStatusResponse']
export type JobStatus = {
  job_id: GeneratedJobStatus['job_id']
  kind?: GeneratedJobStatus['kind']
  status: GeneratedJobStatus['status']
  progress: GeneratedJobStatus['progress']
  elapsed_s: GeneratedJobStatus['elapsed_s']
  timestamps?: GeneratedJobStatus['timestamps']
  artifact?: GeneratedJobStatus['artifact']
  timed_out?: GeneratedJobStatus['timed_out']
  error?: GeneratedJobStatus['error']
  error_code?: GeneratedJobStatus['error_code']
  issues?: ApiValidationIssue[] | null
  result?: JsonObject | null
  result_summary?: JsonObject | null
}

const JOB_STATUSES = new Set<JobStatus['status']>([
  'queued',
  'running',
  'cancellation_requested',
  'cancelled',
  'timed_out',
  'done',
  'error',
  'interrupted',
  'expired',
])

/** Generated from the FastAPI OpenAPI contract (schema.ts). */
export type CostEstimate = components['schemas']['CostEstimateResponse']
export type SweepCostEstimate = components['schemas']['SweepCostEstimateResponse']

type GeneratedScenarioInspection = components['schemas']['ScenarioInspectionResponse']
export type ScenarioInspection = {
  valid: GeneratedScenarioInspection['valid']
  digest: GeneratedScenarioInspection['digest']
  scenario: ScenarioPayload
  effective_digest: GeneratedScenarioInspection['effective_digest']
  effective_scenario: ScenarioPayload
  resolution_time_s: GeneratedScenarioInspection['resolution_time_s']
  warnings: ApiValidationIssue[]
  characterizations: Record<
    'source' | 'channel' | 'detector' | 'timing',
    JsonObject
  >
  cost_estimate: GeneratedScenarioInspection['cost_estimate']
}

type GeneratedCancellationResponse = components['schemas']['CancellationResponse']
export type CancellationResponse = {
  cancelled: GeneratedCancellationResponse['cancelled']
  cancellation_requested?: GeneratedCancellationResponse['cancellation_requested']
  status?: JobStatus['status'] | null
}

export type ExperimentSummary = components['schemas']['ExperimentSummary'] & { __detail?: Experiment }
export type ExperimentPagination = components['schemas']['ExperimentPagination']

type GeneratedExperiment = components['schemas']['ExperimentResponse']
export type Experiment = {
  id: GeneratedExperiment['id']
  origin: GeneratedExperiment['origin']
  name: GeneratedExperiment['name']
  schema_version: GeneratedExperiment['schema_version']
  digest: GeneratedExperiment['digest']
  scenario: ScenarioPayload
  last_result?: JsonObject | null
  tags: GeneratedExperiment['tags']
  created_at: GeneratedExperiment['created_at']
  updated_at: GeneratedExperiment['updated_at']
  curve_recipes: JsonValue[]
  runs: JsonObject[]
  curves: JsonObject[]
  provenance: JsonObject
}

export type BuiltinPreset = {
  name: string
  digest: string
  scenario: ScenarioPayload
}

export type AxisRequest = {
  target: string
  values:
    | { start: number; stop: number; steps: number; scale?: 'linear' | 'log' }
    | Array<number | string | boolean | null>
  time_axis?: boolean | null
}

export type ApiValidationIssue = {
  loc: string
  msg: string
  code?: string
  severity?: 'error' | 'warning'
  value?: unknown
  context?: Record<string, unknown>
  suggestion?: string
}

export class ApiError extends Error {
  status: number
  issues: ApiValidationIssue[]

  constructor(
    message: string,
    status: number,
    issues: ApiValidationIssue[] = [],
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.issues = issues
  }
}

export async function fetchCatalog(signal?: AbortSignal): Promise<Catalog> {
  const catalog = await fetchJson('/api/catalog', signal, isCatalog)
  hydrateMediumScenarios(catalog)
  return catalog
}

export async function validateScenario(scenario: ScenarioPayload, signal?: AbortSignal): Promise<{
  valid: boolean
  digest: string
  scenario: ScenarioPayload
  issues?: ApiValidationIssue[]
  warnings?: ApiValidationIssue[]
}> {
  return postJson('/api/scenarios/validate', { scenario }, signal, isScenarioValidation)
}

export async function inspectScenario(
  scenario: ScenarioPayload,
  signal?: AbortSignal,
): Promise<ScenarioInspection> {
  return postJson('/api/scenarios/inspect', { scenario }, signal, isScenarioInspection)
}

export async function characterize(
  section: 'source' | 'channel' | 'detector' | 'timing',
  scenario: ScenarioPayload,
  axis?: AxisRequest,
  signal?: AbortSignal,
): Promise<{
  section: string
  state?: Record<string, unknown>
  rows?: Array<Record<string, unknown>>
}> {
  return postJson(`/api/characterize/${section}`, { scenario, axis }, signal, isCharacterizationResponse)
}

export async function previewDynamics(
  scenario: ScenarioPayload,
  signal?: AbortSignal,
): Promise<{ rows: Array<Record<string, unknown>> }> {
  return postJson('/api/dynamics/preview', { scenario }, signal, isRowsResponse)
}

export async function createRun(
  scenario: ScenarioPayload,
  label: string,
  signal?: AbortSignal,
): Promise<components['schemas']['RunCreatedResponse']> {
  return postJson('/api/runs', { scenario, label }, signal, isRunCreated)
}

export async function estimateRun(
  scenario: ScenarioPayload,
  signal?: AbortSignal,
): Promise<CostEstimate> {
  return postJson('/api/runs/estimate', { scenario }, signal, isCostEstimate)
}

export async function fetchRunStatus(jobId: string, signal?: AbortSignal): Promise<JobStatus> {
  return fetchJson(`/api/runs/${jobId}`, signal, isJobStatus)
}

export async function fetchRunResult(
  jobId: string,
  signal?: AbortSignal,
): Promise<JsonObject> {
  return fetchJson(`/api/runs/${jobId}/result`, signal, isJsonObject)
}

export async function cancelRun(
  jobId: string,
  signal?: AbortSignal,
): Promise<CancellationResponse> {
  return deleteJson(`/api/runs/${jobId}`, signal, isCancellationResponse)
}

export async function createSweep(body: {
  scenario: ScenarioPayload
  axis: AxisRequest
  series?: AxisRequest | null
  repeats: number
}, signal?: AbortSignal): Promise<components['schemas']['SweepCreatedResponse']> {
  return postJson('/api/sweeps', body, signal, isSweepCreated)
}

export async function estimateSweep(body: {
  scenario: ScenarioPayload
  axis: AxisRequest
  series?: AxisRequest | null
  repeats: number
}, signal?: AbortSignal): Promise<SweepCostEstimate> {
  return postJson('/api/sweeps/estimate', body, signal, isSweepCostEstimate)
}

export async function fetchSweepStatus(jobId: string, signal?: AbortSignal): Promise<JobStatus> {
  return fetchJson(`/api/sweeps/${jobId}`, signal, isJobStatus)
}

export async function fetchSweepResult(
  jobId: string,
  signal?: AbortSignal,
): Promise<JsonObject> {
  return fetchJson(`/api/sweeps/${jobId}/result`, signal, isJsonObject)
}

export async function cancelSweep(
  jobId: string,
  signal?: AbortSignal,
): Promise<CancellationResponse> {
  return deleteJson(`/api/sweeps/${jobId}`, signal, isCancellationResponse)
}

export type ExperimentListResponse = {
  experiments: ExperimentSummary[]
  pagination?: components['schemas']['ExperimentListResponse']['pagination']
}

export async function listExperiments(
  signal?: AbortSignal,
  options: { limit?: number; offset?: number } = {},
): Promise<ExperimentListResponse> {
  const query = new URLSearchParams()
  if (options.limit != null) query.set('limit', String(options.limit))
  if (options.offset != null) query.set('offset', String(options.offset))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  return fetchJson(`/api/experiments${suffix}`, signal, isExperimentListResponse)
}

export async function createExperiment(body: {
  name: string
  scenario: ScenarioPayload
  tags: string[]
  schema_version?: number
  curve_recipes?: JsonValue[]
  last_result?: JsonObject | null
  runs?: JsonObject[]
  curves?: JsonObject[]
  provenance?: JsonObject
}, signal?: AbortSignal): Promise<{ experiment: Experiment }> {
  return postJson('/api/experiments', body, signal, isExperimentEnvelope)
}

export type ExperimentWrite = {
  name: string
  scenario: ScenarioPayload
  tags: string[]
  schema_version?: number
  curve_recipes?: JsonValue[]
  last_result?: JsonObject | null
  runs?: JsonObject[]
  curves?: JsonObject[]
  provenance?: JsonObject
}

export async function replaceExperiment(
  experimentId: string,
  body: ExperimentWrite,
  signal?: AbortSignal,
): Promise<{ experiment: Experiment }> {
  return putJson(`/api/experiments/${experimentId}`, body, signal, isExperimentEnvelope)
}

export async function importExperiment(
  experiment: JsonObject,
  signal?: AbortSignal,
): Promise<{ experiment: Experiment }> {
  return postJson('/api/experiments/import', { experiment }, signal, isExperimentEnvelope)
}

export async function getExperiment(
  experimentId: string,
  signal?: AbortSignal,
): Promise<{ experiment: Experiment }> {
  return fetchJson(`/api/experiments/${experimentId}`, signal, isExperimentEnvelope)
}

export async function exportExperiment(
  experimentId: string,
  signal?: AbortSignal,
): Promise<{ experiment: Experiment }> {
  return fetchJson(`/api/experiments/${experimentId}/export`, signal, isExperimentEnvelope)
}

export async function deleteExperiment(
  experimentId: string,
  signal?: AbortSignal,
): Promise<{ deleted: boolean }> {
  return deleteJson(`/api/experiments/${experimentId}`, signal, isDeletionResponse)
}

export async function updateExperiment(
  experimentId: string,
  body: { name: string },
  signal?: AbortSignal,
): Promise<{ experiment: Experiment }> {
  return patchJson(`/api/experiments/${experimentId}`, body, signal, isExperimentEnvelope)
}

export async function listPresets(signal?: AbortSignal): Promise<{ presets: BuiltinPreset[] }> {
  return fetchJson('/api/presets', signal, isPresetResponse)
}

type ResponseGuard<T> = (value: unknown) => value is T

async function fetchJson<T>(url: string, signal?: AbortSignal, guard?: ResponseGuard<T>): Promise<T> {
  return requestJson('GET', url, undefined, signal, guard)
}

async function postJson<T>(url: string, body: unknown, signal?: AbortSignal, guard?: ResponseGuard<T>): Promise<T> {
  return requestJson('POST', url, body, signal, guard)
}

async function patchJson<T>(url: string, body: unknown, signal?: AbortSignal, guard?: ResponseGuard<T>): Promise<T> {
  return requestJson('PATCH', url, body, signal, guard)
}

async function putJson<T>(url: string, body: unknown, signal?: AbortSignal, guard?: ResponseGuard<T>): Promise<T> {
  return requestJson('PUT', url, body, signal, guard)
}

async function deleteJson<T>(url: string, signal?: AbortSignal, guard?: ResponseGuard<T>): Promise<T> {
  return requestJson('DELETE', url, undefined, signal, guard)
}

/**
 * GET/DELETE are safe to retry after a network failure or 5xx.  Mutating POST,
 * PUT and PATCH calls deliberately make one attempt: without an idempotency
 * key a retry could duplicate a run or experiment after the server committed.
 */
async function requestJson<T>(
  method: string,
  url: string,
  body: unknown,
  signal: AbortSignal | undefined,
  guard?: ResponseGuard<T>,
): Promise<T> {
  const retryable = method === 'GET' || method === 'DELETE'
  const attempts = retryable ? 3 : 1
  let lastError: unknown
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    signal?.throwIfAborted()
    try {
      const init: RequestInit = { signal }
      if (method !== 'GET') init.method = method
      if (body !== undefined) {
        init.headers = { 'Content-Type': 'application/json' }
        init.body = JSON.stringify(body)
      }
      const response = await fetch(url, init)
      if (response.ok) {
        let payload: unknown
        try {
          payload = await response.json()
        } catch {
          throw new ApiError(`${method} ${url} returned invalid JSON`, 502)
        }
        if (guard && !guard(payload)) {
          throw new ApiError(`${method} ${url} returned an invalid response shape`, 502)
        }
        return payload as T
      }
      const error = await apiError(response, `${method} ${url} failed with ${response.status}`)
      if (!retryable || response.status < 500 || attempt === attempts - 1) throw error
      lastError = error
    } catch (error) {
      if (isAbortError(error)) throw error
      lastError = error
      if (!retryable || attempt === attempts - 1 || error instanceof ApiError && error.status < 500) throw error
    }
    await retryDelay(attempt, signal)
  }
  throw lastError instanceof Error ? lastError : new Error(`${method} ${url} failed`)
}

async function retryDelay(attempt: number, signal?: AbortSignal): Promise<void> {
  const base = Math.min(1_000, 100 * 2 ** attempt)
  const jitter = Math.round(base * (0.5 + Math.random() * 0.5))
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, jitter)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    }, { once: true })
  })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isJsonObject(value: unknown): value is JsonObject {
  return isRecord(value)
}

function isCharacterizationResponse(value: unknown): value is { section: string; state?: Record<string, unknown>; rows?: Array<Record<string, unknown>> } {
  return isRecord(value) && typeof value.section === 'string' && (!('state' in value) || isRecord(value.state)) && (!('rows' in value) || Array.isArray(value.rows) && value.rows.every(isRecord))
}

function isRowsResponse(value: unknown): value is { rows: Array<Record<string, unknown>> } {
  return isRecord(value) && Array.isArray(value.rows) && value.rows.every(isRecord)
}

function isCatalog(value: unknown): value is Catalog {
  if (!isRecord(value) || !Array.isArray(value.sections) || !Array.isArray(value.metrics)) {
    return false
  }
  // Legacy payloads omit the metadata block and remain readable.  Once a
  // block is present, reject malformed/future versions loudly so scientific
  // fields are never silently interpreted with a newer contract.
  if ('metadata_version' in value) {
    if (value.metadata_version !== DOMAIN_METADATA_VERSION) return false
    if (!isRecord(value.default_scenario) || !isRecord(value.field_defaults)) return false
    if (!Array.isArray(value.fields) || !Array.isArray(value.media)) return false
    if (!value.fields.every(isCatalogMetadataField) || !value.media.every(isCatalogMediumMetadata)) return false
    if ('default_medium_id' in value && typeof value.default_medium_id !== 'string') return false
  }
  return true
}

function isCatalogMetadataField(value: unknown): value is CatalogMetadataField {
  return isRecord(value)
    && typeof value.key === 'string'
    && 'default' in value
    && ('unit' in value ? value.unit === null || typeof value.unit === 'string' : true)
    && (!('options' in value) || value.options === null || Array.isArray(value.options) && value.options.every((item) => typeof item === 'string'))
}

function isCatalogMediumMetadata(value: unknown): value is CatalogMediumMetadata {
  return isRecord(value)
    && typeof value.id === 'string'
    && Array.isArray(value.channel_kinds)
    && value.channel_kinds.every((kind) => typeof kind === 'string')
    && isRecord(value.scenario)
}

function isCostEstimate(value: unknown): value is CostEstimate {
  return isRecord(value)
    && value.estimate_kind === 'upper_bound'
    && typeof value.evaluations === 'number'
    && typeof value.pulses_per_evaluation === 'number'
    && typeof value.total_pulse_events === 'number'
    && typeof value.estimated_max_circuits === 'number'
    && typeof value.shots_per_circuit === 'number'
    && typeof value.estimated_max_shots === 'number'
    && typeof value.estimated_stored_events === 'number'
    && (value.backend === 'statevector' || value.backend === 'aer' || value.backend === 'mixed')
    && typeof value.full_event_log === 'boolean'
    && Array.isArray(value.warnings)
    && value.warnings.every((item) => typeof item === 'string')
}

function isSweepCostEstimate(value: unknown): value is SweepCostEstimate {
  return isCostEstimate(value)
    && typeof value.estimated_payload_bytes === 'number'
    && typeof value.estimated_artifact_bytes === 'number'
    && typeof value.estimated_total_bytes === 'number'
}

function isRunCreated(value: unknown): value is components['schemas']['RunCreatedResponse'] {
  return isRecord(value) && typeof value.job_id === 'string' && isJobStatusValue(value.status) && typeof value.digest === 'string' && isCostEstimate(value.cost_estimate)
}

function isSweepCreated(value: unknown): value is components['schemas']['SweepCreatedResponse'] {
  return isRecord(value) && typeof value.job_id === 'string' && isJobStatusValue(value.status) && isSweepCostEstimate(value.cost_estimate)
}

function isJobStatus(value: unknown): value is JobStatus {
  return isRecord(value)
    && typeof value.job_id === 'string'
    && isJobStatusValue(value.status)
    && isRecord(value.progress)
    && typeof value.progress.done === 'number'
    && typeof value.progress.total === 'number'
}

function isCancellationResponse(value: unknown): value is CancellationResponse {
  return isRecord(value)
    && typeof value.cancelled === 'boolean'
    && (!('status' in value) || value.status == null || isJobStatusValue(value.status))
}

function isJobStatusValue(value: unknown): value is JobStatus['status'] {
  return typeof value === 'string' && JOB_STATUSES.has(value as JobStatus['status'])
}

function isDeletionResponse(value: unknown): value is { deleted: boolean } {
  return isRecord(value) && typeof value.deleted === 'boolean'
}

function isScenarioValidation(value: unknown): value is { valid: boolean; digest: string; scenario: ScenarioPayload; warnings?: ApiValidationIssue[] } {
  return isRecord(value) && typeof value.valid === 'boolean' && typeof value.digest === 'string' && isRecord(value.scenario) && (!('warnings' in value) || Array.isArray(value.warnings))
}

function isScenarioInspection(value: unknown): value is ScenarioInspection {
  if (!isScenarioValidation(value)) return false
  const candidate = value as unknown as Record<string, unknown>
  return typeof candidate.effective_digest === 'string' && isRecord(candidate.effective_scenario) && typeof candidate.resolution_time_s === 'number' && isRecord(candidate.characterizations) && isCostEstimate(candidate.cost_estimate)
}

function isExperimentListResponse(value: unknown): value is ExperimentListResponse {
  if (!isRecord(value) || !Array.isArray(value.experiments)) return false
  if (value.experiments.every(isExperimentSummary)) return true
  // Compatibility reader for pre-pagination clients that returned full
  // documents.  The private detail reference is never emitted by the API;
  // it only avoids a second request for an already-loaded legacy response.
  if (!value.experiments.every(isLegacyExperiment)) return false
  value.experiments = value.experiments.map((item) => {
    const detail = item as Record<string, unknown> & { __detail?: Experiment }
    const summary = summaryFromExperiment(detail)
    summary.__detail = detail as unknown as Experiment
    return summary
  })
  return true
}

function isExperimentSummary(value: unknown): value is ExperimentSummary {
  return isRecord(value)
    && typeof value.id === 'string'
    && value.origin === 'user'
    && typeof value.name === 'string'
    && typeof value.schema_version === 'number'
    && typeof value.digest === 'string'
    && Array.isArray(value.tags)
    && value.tags.every((tag) => typeof tag === 'string')
    && typeof value.created_at === 'string'
    && typeof value.updated_at === 'string'
    && typeof value.runs_count === 'number'
    && typeof value.curves_count === 'number'
}

function isLegacyExperiment(value: unknown): value is Record<string, unknown> {
  return isRecord(value) && typeof value.id === 'string' && value.origin === 'user' && typeof value.name === 'string' && typeof value.digest === 'string' && isRecord(value.scenario) && Array.isArray(value.tags) && typeof value.created_at === 'string' && typeof value.updated_at === 'string'
}

function summaryFromExperiment(value: Record<string, unknown>): ExperimentSummary {
  return {
    id: String(value.id),
    origin: 'user',
    name: String(value.name),
    schema_version: typeof value.schema_version === 'number' ? value.schema_version : 2,
    digest: String(value.digest),
    tags: Array.isArray(value.tags) ? value.tags.filter((tag): tag is string => typeof tag === 'string') : [],
    created_at: String(value.created_at),
    updated_at: String(value.updated_at),
    runs_count: Array.isArray(value.runs) ? value.runs.length : 0,
    curves_count: Array.isArray(value.curves) ? value.curves.length : 0,
  }
}

function isExperimentEnvelope(value: unknown): value is { experiment: Experiment } {
  if (!isRecord(value) || !isRecord(value.experiment)) return false
  const experiment = value.experiment
  if (typeof experiment.id !== 'string' || experiment.origin !== 'user' || typeof experiment.name !== 'string' || typeof experiment.digest !== 'string' || !isRecord(experiment.scenario) || !Array.isArray(experiment.tags) || typeof experiment.created_at !== 'string' || typeof experiment.updated_at !== 'string') return false
  normaliseExperiment(experiment)
  return true
}

function normaliseExperiment(value: Record<string, unknown>): void {
  if (!Array.isArray(value.curve_recipes)) value.curve_recipes = []
  if (!Array.isArray(value.runs)) value.runs = []
  if (!Array.isArray(value.curves)) value.curves = []
  if (!isRecord(value.provenance)) value.provenance = {}
}

function isPresetResponse(value: unknown): value is { presets: BuiltinPreset[] } {
  return isRecord(value) && Array.isArray(value.presets) && value.presets.every((preset) => isRecord(preset) && typeof preset.name === 'string' && typeof preset.digest === 'string' && isRecord(preset.scenario))
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
    || isRecord(error) && error.name === 'AbortError'
}

function isValidationIssue(value: unknown): value is ApiValidationIssue {
  return isRecord(value)
    && typeof value.loc === 'string'
    && typeof value.msg === 'string'
    && (!('code' in value) || typeof value.code === 'string')
    && (!('severity' in value) || value.severity === 'error' || value.severity === 'warning')
}

async function apiError(response: Response, fallback: string): Promise<ApiError> {
  try {
    const payload: unknown = await response.json()
    const record = isRecord(payload) ? payload : {}
    const detail = record.detail
    const message = typeof record.message === 'string'
      ? record.message
      : typeof record.error === 'string'
        ? record.error
        : typeof detail === 'string'
          ? detail
          : isRecord(detail) && typeof detail.message === 'string'
            ? detail.message
        : fallback
    const issues = (Array.isArray(record.errors) ? record.errors : Array.isArray(record.issues) ? record.issues : [])
      .filter(isValidationIssue)
    return new ApiError(
      message,
      response.status,
      issues,
    )
  } catch {
    return new ApiError(fallback, response.status)
  }
}
