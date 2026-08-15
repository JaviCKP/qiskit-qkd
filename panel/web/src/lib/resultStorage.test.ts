import { afterEach, expect, test, vi } from 'vitest'

import {
  clearResultStorageDiagnostic,
  compactWorkspaceState,
  createResultStorage,
  getResultStorageDiagnostic,
  RESULT_STORAGE_VERSION,
} from './resultStorage'

afterEach(() => {
  vi.restoreAllMocks()
  clearResultStorageDiagnostic()
})

test('compacts a legacy 20k-event workspace before stringify while preserving job metadata', () => {
  const events = Array.from({ length: 20_000 }, (_, index) => ({ index, detected: index % 2 === 0, timing_status: 'ok' }))
  const state = {
    scenario: { schema_version: 2 },
    runs: [{ jobId: 'job-1', label: 'run', result: { event_sample: events }, status: { status: 'done', result: { event_sample: events } } }],
    curves: [{ jobId: 'curve-1', result: { rows: events } }],
    activeRun: null,
    activeSweep: null,
  }
  const before = JSON.stringify(state)
  const compacted = compactWorkspaceState(state)
  const after = JSON.stringify(compacted)

  expect(before.length).toBeGreaterThan(1_000_000)
  expect(after.length).toBeLessThan(before.length / 10)
  expect(after).not.toContain('timing_status')
  expect(compacted).toMatchObject({ runs: [{ jobId: 'job-1', result: {}, status: { status: 'done' } }], curves: [{ jobId: 'curve-1', result: {} }] })
})

test('never writes a legacy 20k-event payload or duplicate event-log keys', () => {
  const events = Array.from({ length: 20_000 }, (_, index) => ({ index, timing_status: 'ok' }))
  const values = new Map<string, string>()
  const storage = createResultStorage({
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  })

  storage.setItem('workspace', JSON.stringify({
    version: 2,
    state: {
      runs: [{ jobId: 'legacy-job', result: { event_sample: events }, status: { result: { event_sample: events } } }],
      curves: [{ jobId: 'legacy-curve', result: { rows: events } }],
    },
  }))

  const persisted = values.get('workspace') ?? ''
  expect(persisted).toContain('legacy-job')
  expect(persisted).toContain('legacy-curve')
  expect(persisted).not.toContain('timing_status')
  expect(persisted).not.toContain('event_sample')
  expect(persisted).not.toContain('"rows"')
  expect(persisted.match(/legacy-job/g)).toHaveLength(1)
})

test('ignores corrupt JSON and future versions without crashing or deleting a downgrade copy', () => {
  const values = new Map<string, string>([
    ['corrupt', '{not-json'],
    ['future', JSON.stringify({ version: RESULT_STORAGE_VERSION + 1, state: { runs: [] } })],
  ])
  const backing = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  }
  const storage = createResultStorage(backing)

  expect(storage.getItem('corrupt')).toBeNull()
  expect(values.has('corrupt')).toBe(false)
  expect(storage.getItem('future')).toBeNull()
  expect(values.has('future')).toBe(true)
  expect(getResultStorageDiagnostic()).toMatchObject({ kind: 'future-version', version: RESULT_STORAGE_VERSION + 1 })
})

test('falls back to a compact metadata write when localStorage quota is exhausted', () => {
  const calls: string[] = []
  const backing = {
    getItem: () => null,
    setItem: (_key: string, value: string) => {
      calls.push(value)
      if (calls.length === 1) throw { name: 'QuotaExceededError', code: 22 }
    },
    removeItem: () => undefined,
  }
  const storage = createResultStorage(backing)

  expect(() => storage.setItem('workspace', JSON.stringify({ version: RESULT_STORAGE_VERSION, state: { runs: [{ jobId: 'job-1', result: { rows: [1, 2, 3] } }] } }))).not.toThrow()
  expect(calls).toHaveLength(2)
  expect(calls[1]).toContain('job-1')
  expect(getResultStorageDiagnostic()).toMatchObject({ kind: 'quota', key: 'workspace' })
})
