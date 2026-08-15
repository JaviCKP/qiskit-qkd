import { afterEach, expect, test, vi } from 'vitest'

import { defaultScenario } from '@/features/designer/defaultScenario'
import { ApiError, createRun, createSweep, estimateSweep, fetchCatalog, inspectScenario, listExperiments, DOMAIN_METADATA_VERSION } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('forwards AbortSignal through GET and POST requests', async () => {
  const fetchMock = vi.fn(async (url: string) => url === '/api/catalog'
    ? jsonResponse({ sections: [], metrics: [] })
    : jsonResponse({ valid: true, digest: 'digest', scenario, effective_digest: 'digest', effective_scenario: scenario, resolution_time_s: 0, warnings: [], characterizations: {}, cost_estimate: costEstimate() }))
  vi.stubGlobal('fetch', fetchMock)
  const controller = new AbortController()

  await fetchCatalog(controller.signal)
  const scenario = { ...structuredClone(defaultScenario), pulses: 8 }
  await inspectScenario(scenario, controller.signal)

  expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/catalog', {
    signal: controller.signal,
  })
  expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/scenarios/inspect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario }),
    signal: controller.signal,
  })
})

test('uses generated pagination query and validates lightweight summaries', async () => {
  const fetchMock = vi.fn(async () => jsonResponse({
    experiments: [{ id: 'exp-1', origin: 'user', name: 'Demo', schema_version: 2, digest: 'abc', tags: ['bb84', 'fiber'], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', runs_count: 2, curves_count: 1 }],
    pagination: { offset: 50, limit: 50, total: 51, has_more: false },
  }))
  vi.stubGlobal('fetch', fetchMock)

  const response = await listExperiments(undefined, { limit: 50, offset: 50 })
  expect(response.experiments[0]?.id).toBe('exp-1')
  expect(fetchMock).toHaveBeenCalledWith('/api/experiments?limit=50&offset=50', { signal: undefined })
})

test('rejects malformed or future domain metadata instead of silently using it', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
    sections: [],
    metrics: [],
    metadata_version: DOMAIN_METADATA_VERSION + 1,
    default_scenario: {},
    field_defaults: {},
    fields: [],
    media: [],
  }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(fetchCatalog()).rejects.toBeInstanceOf(ApiError)

  fetchMock.mockResolvedValue(jsonResponse({
    sections: [],
    metrics: [],
    metadata_version: DOMAIN_METADATA_VERSION,
    default_scenario: {},
    field_defaults: {},
    fields: [{ key: 'channel.distance_km' }],
    media: [],
  }))
  await expect(fetchCatalog()).rejects.toBeInstanceOf(ApiError)
})

test('retries idempotent GET on 5xx but never retries a 4xx', async () => {
  const response500 = { ok: false, status: 503, json: async () => ({ message: 'busy' }) } as Response
  const response200 = jsonResponse({ sections: [], metrics: [] })
  const fetchMock = vi.fn().mockResolvedValueOnce(response500).mockResolvedValueOnce(response200)
  vi.stubGlobal('fetch', fetchMock)
  await fetchCatalog()
  expect(fetchMock).toHaveBeenCalledTimes(2)

  const response400 = { ok: false, status: 400, json: async () => ({ message: 'bad request' }) } as Response
  fetchMock.mockReset().mockResolvedValue(response400)
  await expect(fetchCatalog()).rejects.toBeInstanceOf(ApiError)
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

test('creates runs and sweeps with one non-retried POST each', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse({ job_id: 'run-1', status: 'queued', digest: 'digest', cost_estimate: costEstimate() }))
    .mockResolvedValueOnce(jsonResponse({ job_id: 'sweep-1', status: 'queued', cost_estimate: sweepCostEstimate() }))
  vi.stubGlobal('fetch', fetchMock)

  await createRun(defaultScenario, 'run')
  await createSweep({ scenario: defaultScenario, axis: { target: 'channel.distance_km', values: [0, 10] }, repeats: 1 })

  expect(fetchMock).toHaveBeenCalledTimes(2)
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/runs', '/api/sweeps'])
  expect(fetchMock.mock.calls.every(([, init]) => (init as RequestInit).method === 'POST')).toBe(true)
})

test('requires byte admission fields in sweep estimates', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(jsonResponse(costEstimate()))
    .mockResolvedValueOnce(jsonResponse(sweepCostEstimate()))
  vi.stubGlobal('fetch', fetchMock)
  const request = { scenario: defaultScenario, axis: { target: 'channel.distance_km', values: [0, 10] }, repeats: 1 }

  await expect(estimateSweep(request)).rejects.toBeInstanceOf(ApiError)
  await expect(estimateSweep(request)).resolves.toMatchObject({
    estimated_payload_bytes: 1024,
    estimated_artifact_bytes: 2048,
    estimated_total_bytes: 3072,
  })
})

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response
}

function costEstimate() {
  return { estimate_kind: 'upper_bound', evaluations: 1, pulses_per_evaluation: 1, total_pulse_events: 1, estimated_max_circuits: 1, shots_per_circuit: 1, estimated_max_shots: 1, estimated_stored_events: 0, backend: 'statevector', full_event_log: false, warnings: [] }
}

function sweepCostEstimate() {
  return { ...costEstimate(), estimated_payload_bytes: 1024, estimated_artifact_bytes: 2048, estimated_total_bytes: 3072 }
}
