export type HealthStatus = {
  status: 'ok'
  service: string
}

export async function fetchHealthStatus(): Promise<HealthStatus> {
  const response = await fetch('/api/health')

  if (!response.ok) {
    throw new Error(`API health check failed with ${response.status}`)
  }

  return response.json() as Promise<HealthStatus>
}
