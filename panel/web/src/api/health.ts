export type HealthStatus = {
  status: 'ok'
  service: string
}

export async function fetchHealthStatus(signal?: AbortSignal): Promise<HealthStatus> {
  const response = await fetch('/api/health', { signal })

  if (!response.ok) {
    throw new Error(`API health check failed with ${response.status}`)
  }

  const payload: unknown = await response.json()
  if (!isHealthStatus(payload)) {
    throw new Error('API health check returned an invalid response shape')
  }
  return payload
}

function isHealthStatus(value: unknown): value is HealthStatus {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    && (value as Record<string, unknown>).status === 'ok'
    && typeof (value as Record<string, unknown>).service === 'string'
}
