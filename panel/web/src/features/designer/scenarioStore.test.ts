import { beforeEach, expect, test } from 'vitest'

import { DEFAULT_SCENARIO_METADATA_VERSION, defaultScenario } from './defaultScenario'
import {
  useDesignerStore,
  type ActiveRun,
  type ActiveSweep,
  type CurveSnapshot,
  type RunSnapshot,
} from './scenarioStore'

beforeEach(() => {
  localStorage.clear()
  useDesignerStore.setState(useDesignerStore.getInitialState(), true)
})

test('offline fallback is explicit and matches the published fiber workbench shape', () => {
  expect(DEFAULT_SCENARIO_METADATA_VERSION).toBe(1)
  expect(defaultScenario.channel.kind).toBe('fiber')
  expect(defaultScenario.channel.distance_km).toBe(25)
  expect(defaultScenario.source.kind).toBe('decoy_weak_coherent')
  expect(defaultScenario.source.decoy_intensities).toHaveLength(3)
  expect(defaultScenario.detector.kind).toBe('threshold')
})

test('loads a scenario and infers the active medium', () => {
  useDesignerStore.getState().loadScenario({
    ...structuredClone(defaultScenario),
    schema_version: 1,
    channel: { ...defaultScenario.channel, kind: 'underwater' },
    metadata: {},
  })

  expect(useDesignerStore.getState().activeMediumId).toBe('underwater')
})

test('selects a medium and loads its scenario defaults', () => {
  useDesignerStore.getState().selectMedium('ideal')

  expect(useDesignerStore.getState().activeMediumId).toBe('ideal')
  expect(useDesignerStore.getState().scenario.channel).toMatchObject({ kind: 'ideal' })
  expect(useDesignerStore.getState().scenario.metadata).toMatchObject({ mediumId: 'ideal' })
})

test('updating channel kind to custom keeps explicit custom mode', () => {
  useDesignerStore.getState().selectMedium('custom')
  useDesignerStore.getState().updateField('channel.kind', 'fiber')

  expect(useDesignerStore.getState().activeMediumId).toBe('custom')
  expect(useDesignerStore.getState().scenario.channel).toMatchObject({ kind: 'fiber' })
})

test('clones loaded scenarios to avoid external mutation', () => {
  const external = {
    ...structuredClone(defaultScenario),
    schema_version: 1,
    channel: { ...defaultScenario.channel, kind: 'fiber', distance_km: 25 },
    metadata: {},
  }

  useDesignerStore.getState().loadScenario(external)
  external.channel.distance_km = 90

  expect(useDesignerStore.getState().scenario.channel).toMatchObject({ distance_km: 25 })
})

test('tracks edited fields and resets provenance when selecting a preset', () => {
  useDesignerStore.getState().updateField('channel.distance_km', 40)
  expect(useDesignerStore.getState().editedFields).toEqual(['channel.distance_km'])

  useDesignerStore.getState().selectMedium('ideal')
  expect(useDesignerStore.getState().editedFields).toEqual([])
})

test('switches prepared scenarios without discarding completed runs or curves', () => {
  const run = completedRun()
  const curve = completedCurve()
  useDesignerStore.setState({ runs: [run], curves: [curve] })

  useDesignerStore.getState().selectMedium('underwater')

  expect(useDesignerStore.getState().activeMediumId).toBe('underwater')
  expect(useDesignerStore.getState().runs).toEqual([run])
  expect(useDesignerStore.getState().curves).toEqual([curve])
})

test('persists active jobs so polling can recover after a reload', () => {
  const activeRun = {
    jobId: 'run-active',
    label: 'Ejecución recuperable',
    digest: '0123456789abcdef',
    scenario: structuredClone(defaultScenario),
    startedAt: '2026-08-09T10:00:00Z',
    costEstimate: costEstimate(),
    status: null,
  } satisfies ActiveRun
  const activeSweep = {
    jobId: 'sweep-active',
    baseDigest: activeRun.digest,
    baseLabel: activeRun.label,
    scenario: structuredClone(defaultScenario),
    axis: { target: 'channel.distance_km', values: [0, 10] },
    series: null,
    metric: 'qber',
    repeats: 1,
    startedAt: activeRun.startedAt,
    costEstimate: costEstimate(),
    status: null,
  } satisfies ActiveSweep

  useDesignerStore.getState().beginRun(activeRun)
  useDesignerStore.getState().beginSweep(activeSweep)

  const persisted = JSON.parse(localStorage.getItem('qkd-panel-workspace-v2') ?? '{}')
  expect(persisted.state.activeRun).toMatchObject({ jobId: 'run-active', status: null })
  expect(persisted.state.activeSweep).toMatchObject({ jobId: 'sweep-active', status: null })
})

function costEstimate() {
  return {
    estimate_kind: 'upper_bound' as const,
    evaluations: 1,
    pulses_per_evaluation: 1024,
    total_pulse_events: 1024,
    estimated_max_circuits: 1024,
    shots_per_circuit: 1,
    estimated_max_shots: 1024,
    estimated_stored_events: 0,
    backend: 'statevector' as const,
    full_event_log: false,
    warnings: [],
  }
}

function completedRun(): RunSnapshot {
  return {
    jobId: 'run-completed',
    label: 'Run conservado',
    digest: 'run-digest',
    scenario: structuredClone(defaultScenario),
    seed: defaultScenario.seed,
    startedAt: '2026-08-09T10:00:00Z',
    completedAt: '2026-08-09T10:00:01Z',
    status: {
      job_id: 'run-completed',
      status: 'done',
      progress: { done: 1, total: 1 },
      elapsed_s: 1,
    },
    result: {},
    costEstimate: costEstimate(),
  }
}

function completedCurve(): CurveSnapshot {
  return {
    jobId: 'sweep-completed',
    baseDigest: 'run-digest',
    baseLabel: 'Run conservado',
    scenario: structuredClone(defaultScenario),
    axis: { target: 'channel.distance_km', values: [0, 10] },
    series: null,
    metric: 'qber',
    repeats: 1,
    createdAt: '2026-08-09T10:00:02Z',
    result: {},
    costEstimate: costEstimate(),
  }
}
