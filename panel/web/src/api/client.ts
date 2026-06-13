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
): Promise<{ section: string; state: Record<string, unknown> }> {
  return postJson(`/api/characterize/${section}`, { scenario })
}

export async function previewDynamics(
  scenario: ScenarioPayload,
): Promise<{ rows: Array<Record<string, unknown>> }> {
  return postJson('/api/dynamics/preview', { scenario })
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

async function apiError(response: Response, fallback: string): Promise<ApiError> {
  try {
    const payload = (await response.json()) as { errors?: ApiValidationIssue[] }
    return new ApiError(fallback, response.status, payload.errors ?? [])
  } catch {
    return new ApiError(fallback, response.status)
  }
}
