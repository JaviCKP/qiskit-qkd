import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type { Experiment } from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'
import { useDesignerStore } from '@/features/designer/scenarioStore'

import { LibraryView } from './LibraryView'

const summary = {
  id: 'exp-1',
  origin: 'user' as const,
  name: 'Resumen ligero',
  schema_version: 2,
  digest: 'digest-1',
  tags: ['bb84', 'fiber'],
  created_at: '2026-08-09T10:00:00Z',
  updated_at: '2026-08-09T10:00:00Z',
  runs_count: 2,
  curves_count: 1,
}

const detail: Experiment = {
  ...summary,
  scenario: structuredClone(defaultScenario),
  last_result: null,
  curve_recipes: [],
  runs: [],
  curves: [],
  provenance: {},
}

let fetchMock: ReturnType<typeof vi.fn>
let queryClient: QueryClient

beforeEach(() => {
  localStorage.clear()
  useDesignerStore.setState(useDesignerStore.getInitialState(), true)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url === '/api/experiments?limit=50&offset=0') return jsonResponse({ experiments: [summary], pagination: { offset: 0, limit: 50, total: 1, has_more: false } })
    if (url === '/api/presets') return jsonResponse({ presets: [] })
    if (url === '/api/experiments/exp-1') return jsonResponse({ experiment: detail })
    throw new Error(`Unexpected URL ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  queryClient.clear()
  vi.unstubAllGlobals()
})

test('fetches summaries once and loads one detail only when opening', async () => {
  const opened = vi.fn()
  render(<QueryClientProvider client={queryClient}><LibraryView onOpenExperiment={opened} /></QueryClientProvider>)

  expect(await screen.findByRole('heading', { name: 'Resumen ligero' })).toBeTruthy()
  expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual(['/api/experiments?limit=50&offset=0', '/api/presets'])

  fireEvent.click(screen.getByRole('button', { name: 'Abrir' }))
  await waitFor(() => expect(opened).toHaveBeenCalledTimes(1))
  expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual(['/api/experiments?limit=50&offset=0', '/api/presets', '/api/experiments/exp-1'])
  expect(useDesignerStore.getState().sourceExperimentId).toBe('exp-1')
})

test('summary payload is bounded and does not carry scenario or result blobs', () => {
  const payload = { experiments: [summary] }
  const encoded = JSON.stringify(payload)
  expect(new TextEncoder().encode(encoded).byteLength).toBeLessThan(1_000)
  expect(encoded).not.toContain('scenario')
  expect(encoded).not.toContain('result')
})

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}
