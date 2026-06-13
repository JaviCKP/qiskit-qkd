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
}

export type CatalogSection = {
  key: string
  label_es: string
  fields: CatalogField[]
}

export type Catalog = {
  sections: CatalogSection[]
  metrics: Array<{ key: string; label_es: string; unit: string | null }>
}

export type ScenarioPayload = Record<string, unknown>

export type JobStatus = {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  progress: { done: number; total: number }
  elapsed_s: number
  error?: string
  result?: Record<string, unknown>
  result_summary?: Record<string, unknown>
}

export type Experiment = {
  id: string
  name: string
  digest: string
  scenario: ScenarioPayload
  tags: string[]
  created_at: string
  updated_at: string
  last_result?: Record<string, unknown> | null
  curve_recipes?: unknown[]
}

export type AxisRequest = {
  target: string
  values:
    | { start: number; stop: number; steps: number; scale?: 'linear' | 'log' }
    | Array<number | string | boolean | null>
}

export type ApiValidationIssue = {
  loc: string
  msg: string
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

export async function fetchCatalog(): Promise<Catalog> {
  return fetchJson('/api/catalog')
}

export async function validateScenario(scenario: ScenarioPayload): Promise<{
  valid: boolean
  digest: string
  scenario: ScenarioPayload
}> {
  return postJson('/api/scenarios/validate', { scenario })
}

export async function characterize(
  section: 'source' | 'channel' | 'detector' | 'timing',
  scenario: ScenarioPayload,
  axis?: AxisRequest,
): Promise<{
  section: string
  state?: Record<string, unknown>
  rows?: Array<Record<string, unknown>>
}> {
  return postJson(`/api/characterize/${section}`, { scenario, axis })
}

export async function previewDynamics(
  scenario: ScenarioPayload,
): Promise<{ rows: Array<Record<string, unknown>> }> {
  return postJson('/api/dynamics/preview', { scenario })
}

export async function createRun(
  scenario: ScenarioPayload,
  label: string,
): Promise<{ job_id: string; status: string; digest: string }> {
  return postJson('/api/runs', { scenario, label })
}

export async function fetchRunStatus(jobId: string): Promise<JobStatus> {
  return fetchJson(`/api/runs/${jobId}`)
}

export async function fetchRunResult(jobId: string): Promise<Record<string, unknown>> {
  return fetchJson(`/api/runs/${jobId}/result`)
}

export async function cancelRun(jobId: string): Promise<{ cancelled: boolean }> {
  return deleteJson(`/api/runs/${jobId}`)
}

export async function createSweep(body: {
  scenario: ScenarioPayload
  axis: AxisRequest
  series?: AxisRequest | null
  repeats: number
}): Promise<{ job_id: string; status: string }> {
  return postJson('/api/sweeps', body)
}

export async function fetchSweepStatus(jobId: string): Promise<JobStatus> {
  return fetchJson(`/api/sweeps/${jobId}`)
}

export async function cancelSweep(jobId: string): Promise<{ cancelled: boolean }> {
  return deleteJson(`/api/sweeps/${jobId}`)
}

export async function listExperiments(): Promise<{ experiments: Experiment[] }> {
  return fetchJson('/api/experiments')
}

export async function createExperiment(body: {
  name: string
  scenario: ScenarioPayload
  tags: string[]
  curve_recipes?: unknown[]
  last_result?: Record<string, unknown> | null
}): Promise<{ experiment: Experiment }> {
  return postJson('/api/experiments', body)
}

export async function importExperiment(
  experiment: Record<string, unknown>,
): Promise<{ experiment: Experiment }> {
  return postJson('/api/experiments/import', { experiment })
}

export async function getExperiment(
  experimentId: string,
): Promise<{ experiment: Experiment }> {
  return fetchJson(`/api/experiments/${experimentId}`)
}

export async function exportExperiment(
  experimentId: string,
): Promise<{ experiment: Experiment }> {
  return fetchJson(`/api/experiments/${experimentId}/export`)
}

export async function deleteExperiment(
  experimentId: string,
): Promise<{ deleted: boolean }> {
  return deleteJson(`/api/experiments/${experimentId}`)
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw await apiError(response, `GET ${url} failed with ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw await apiError(response, `POST ${url} failed with ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function deleteJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { method: 'DELETE' })
  if (!response.ok) {
    throw await apiError(response, `DELETE ${url} failed with ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function apiError(response: Response, fallback: string): Promise<ApiError> {
  try {
    const payload = (await response.json()) as { errors?: ApiValidationIssue[] }
    return new ApiError(fallback, response.status, payload.errors ?? [])
  } catch {
    return new ApiError(fallback, response.status)
  }
}
