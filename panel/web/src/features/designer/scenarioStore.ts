import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type {
  AxisRequest,
  CostEstimate,
  Experiment,
  JobStatus,
  JsonObject,
  ScenarioPayload,
} from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'
import {
  inferMediumFromScenario,
  mediumDefinitions,
  scenarioForMedium,
  type MediumId,
} from '@/features/lab/mediums'
import { cloneJson, writeTarget } from '@/features/shared/scenarioPaths'
import {
  compactWorkspaceState,
  RESULT_STORAGE_VERSION,
  resultStorage,
} from '@/lib/resultStorage'

export type RunSnapshot = {
  jobId: string
  label: string
  digest: string
  scenario: ScenarioPayload
  seed: number
  startedAt: string
  completedAt: string
  status: JobStatus
  result: JsonObject
  costEstimate: CostEstimate
}

export type CurveSnapshot = {
  jobId: string
  baseDigest: string
  baseLabel: string
  scenario: ScenarioPayload
  axis: AxisRequest
  series: AxisRequest | null
  metric: string
  repeats: number
  createdAt: string
  result: JsonObject
  costEstimate: CostEstimate
}

export type ActiveRun = {
  jobId: string
  label: string
  digest: string
  scenario: ScenarioPayload
  startedAt: string
  costEstimate: CostEstimate
  status: JobStatus | null
}

export type ActiveSweep = {
  jobId: string
  baseDigest: string
  baseLabel: string
  scenario: ScenarioPayload
  axis: AxisRequest
  series: AxisRequest | null
  metric: string
  repeats: number
  startedAt: string
  costEstimate: CostEstimate
  status: JobStatus | null
}

type DesignerState = {
  scenario: ScenarioPayload
  activeMediumId: MediumId
  experimentName: string
  sourceExperimentId: string | null
  hasUnsavedChanges: boolean
  editedFields: string[]
  runs: RunSnapshot[]
  curves: CurveSnapshot[]
  activeRun: ActiveRun | null
  activeSweep: ActiveSweep | null
  loadScenario: (scenario: ScenarioPayload) => void
  loadExperiment: (experiment: Experiment) => void
  selectMedium: (mediumId: MediumId) => void
  setExperimentName: (name: string) => void
  updateField: (target: string, value: unknown) => void
  beginRun: (run: ActiveRun) => void
  updateRunStatus: (status: JobStatus) => void
  finishRun: (run: RunSnapshot) => void
  hydrateRunResult: (jobId: string, result: JsonObject) => void
  clearActiveRun: () => void
  beginSweep: (sweep: ActiveSweep) => void
  updateSweepStatus: (status: JobStatus) => void
  finishSweep: (sweep: CurveSnapshot) => void
  hydrateCurveResult: (jobId: string, result: JsonObject) => void
  clearActiveSweep: () => void
  markSaved: (experiment: Experiment) => void
  duplicateWorkspace: () => void
}

const initialWorkspace = {
  scenario: defaultScenario,
  activeMediumId: inferMediumFromScenario(defaultScenario),
  experimentName: 'Experimento de fibra',
  sourceExperimentId: null,
  hasUnsavedChanges: false,
  editedFields: [],
  runs: [],
  curves: [],
  activeRun: null,
  activeSweep: null,
}

export const useDesignerStore = create<DesignerState>()(persist((set) => ({
  ...initialWorkspace,
  loadScenario: (scenario) => {
    const nextScenario = cloneJson(scenario)
    set({
      scenario: nextScenario,
      activeMediumId: inferMediumFromScenario(nextScenario),
      sourceExperimentId: null,
      hasUnsavedChanges: false,
      editedFields: [],
      runs: [],
      curves: [],
      activeRun: null,
      activeSweep: null,
    })
  },
  loadExperiment: (experiment) => {
    const nextScenario = cloneJson(experiment.scenario)
    set({
      scenario: nextScenario,
      activeMediumId: inferMediumFromScenario(nextScenario),
      experimentName: experiment.name,
      sourceExperimentId: experiment.id,
      hasUnsavedChanges: false,
      editedFields: [],
      runs: experiment.runs.map(runFromJson).filter(isPresent).slice(-20),
      curves: experiment.curves.map(curveFromJson).filter(isPresent).slice(-20),
      activeRun: null,
      activeSweep: null,
    })
  },
  selectMedium: (mediumId) =>
    set({
      scenario: scenarioForMedium(mediumId),
      activeMediumId: mediumId,
      experimentName: mediumId === 'custom'
        ? 'Experimento personalizado'
        : `Experimento · ${mediumDefinitions[mediumId].shortLabel}`,
      sourceExperimentId: null,
      hasUnsavedChanges: true,
      editedFields: [],
    }),
  setExperimentName: (experimentName) => set((state) => ({
    experimentName,
    hasUnsavedChanges: true,
    editedFields: state.editedFields.includes('experiment.name')
      ? state.editedFields
      : [...state.editedFields, 'experiment.name'],
  })),
  updateField: (target, value) =>
    set((state) => {
      const editedFields = state.editedFields.includes(target)
        ? state.editedFields
        : [...state.editedFields, target]
      const updatedScenario = writeTarget(state.scenario, target, value)
      if (target === 'channel.kind') {
        if (state.activeMediumId === 'custom') {
          return {
            scenario: updatedScenario,
            activeMediumId: 'custom',
            hasUnsavedChanges: true,
            editedFields,
          }
        }
        const metadata = { ...updatedScenario.metadata }
        delete metadata.mediumId
        const scenarioWithoutMedium = { ...updatedScenario, metadata }
        const activeMediumId = inferMediumFromScenario(scenarioWithoutMedium)
        return {
          scenario: {
            ...scenarioWithoutMedium,
            metadata: { ...metadata, mediumId: activeMediumId },
          },
            activeMediumId,
          hasUnsavedChanges: true,
            editedFields,
        }
      }
      return {
        scenario: updatedScenario,
        activeMediumId: state.activeMediumId,
        hasUnsavedChanges: true,
        editedFields,
      }
    }),
  beginRun: (activeRun) => set({ activeRun }),
  updateRunStatus: (status) => set((state) => ({
    activeRun: state.activeRun ? { ...state.activeRun, status } : null,
  })),
  finishRun: (run) => set((state) => ({
    runs: [...state.runs, cloneJson(run)].slice(-20),
    activeRun: null,
  })),
  hydrateRunResult: (jobId, result) => set((state) => ({
    runs: state.runs.map((run) => run.jobId === jobId
      ? { ...run, result: cloneJson(result) }
      : run),
  })),
  clearActiveRun: () => set({ activeRun: null }),
  beginSweep: (activeSweep) => set({ activeSweep }),
  updateSweepStatus: (status) => set((state) => ({
    activeSweep: state.activeSweep ? { ...state.activeSweep, status } : null,
  })),
  finishSweep: (curve) => set((state) => ({
    curves: [...state.curves, cloneJson(curve)].slice(-20),
    activeSweep: null,
  })),
  hydrateCurveResult: (jobId, result) => set((state) => ({
    curves: state.curves.map((curve) => curve.jobId === jobId
      ? { ...curve, result: cloneJson(result) }
      : curve),
  })),
  clearActiveSweep: () => set({ activeSweep: null }),
  markSaved: (experiment) => set({
    experimentName: experiment.name,
    sourceExperimentId: experiment.id,
    hasUnsavedChanges: false,
    editedFields: [],
  }),
  duplicateWorkspace: () => set((state) => ({
    experimentName: `${state.experimentName} copia`,
    sourceExperimentId: null,
    hasUnsavedChanges: true,
    editedFields: state.editedFields.includes('experiment.name')
      ? state.editedFields
      : [...state.editedFields, 'experiment.name'],
  })),
}), {
  name: 'qkd-panel-workspace-v2',
  version: RESULT_STORAGE_VERSION,
  storage: createJSONStorage(() => resultStorage),
  // Compact before Zustand serializes.  This is the important distinction
  // from filtering in the StateStorage adapter: JSON.stringify never sees
  // event samples or complete curve rows in the first place.
  partialize: (state) => compactWorkspaceState({
    scenario: state.scenario,
    activeMediumId: state.activeMediumId,
    experimentName: state.experimentName,
    sourceExperimentId: state.sourceExperimentId,
    hasUnsavedChanges: state.hasUnsavedChanges,
    editedFields: state.editedFields,
    runs: state.runs,
    curves: state.curves,
    activeRun: state.activeRun,
    activeSweep: state.activeSweep,
  }) as Partial<DesignerState>,
  migrate: (persistedState) => compactWorkspaceState(persistedState) as DesignerState,
}))

export function runToJson(run: RunSnapshot): JsonObject {
  return cloneJson(run) as unknown as JsonObject
}

export function curveToJson(curve: CurveSnapshot): JsonObject {
  return cloneJson(curve) as unknown as JsonObject
}

function runFromJson(value: JsonObject): RunSnapshot | null {
  if (
    typeof value.jobId !== 'string' ||
    typeof value.label !== 'string' ||
    typeof value.digest !== 'string' ||
    typeof value.seed !== 'number' ||
    typeof value.startedAt !== 'string' ||
    typeof value.completedAt !== 'string' ||
    !value.scenario ||
    !value.status ||
    !value.costEstimate
  ) {
    return null
  }
  return {
    ...cloneJson(value),
    result: value.result && typeof value.result === 'object' ? cloneJson(value.result) : {},
  } as unknown as RunSnapshot
}

function curveFromJson(value: JsonObject): CurveSnapshot | null {
  if (
    typeof value.jobId !== 'string' ||
    typeof value.baseDigest !== 'string' ||
    typeof value.baseLabel !== 'string' ||
    typeof value.metric !== 'string' ||
    typeof value.repeats !== 'number' ||
    typeof value.createdAt !== 'string' ||
    !value.scenario ||
    !value.axis ||
    !value.costEstimate
  ) {
    return null
  }
  return {
    ...cloneJson(value),
    result: value.result && typeof value.result === 'object' ? cloneJson(value.result) : {},
  } as unknown as CurveSnapshot
}

function isPresent<T>(value: T | null): value is T {
  return value !== null
}
