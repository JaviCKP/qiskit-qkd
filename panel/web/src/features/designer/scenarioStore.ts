import { create } from 'zustand'

import type { ScenarioPayload } from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'
import {
  inferMediumFromScenario,
  scenarioForMedium,
  type MediumId,
} from '@/features/lab/mediums'
import { cloneJson, writeTarget } from '@/features/shared/scenarioPaths'

type DesignerState = {
  scenario: ScenarioPayload
  activeMediumId: MediumId
  loadScenario: (scenario: ScenarioPayload) => void
  selectMedium: (mediumId: MediumId) => void
  updateField: (target: string, value: unknown) => void
}

export const useDesignerStore = create<DesignerState>((set) => ({
  scenario: defaultScenario,
  activeMediumId: inferMediumFromScenario(defaultScenario),
  loadScenario: (scenario) => {
    const nextScenario = cloneJson(scenario)
    set({
      scenario: nextScenario,
      activeMediumId: inferMediumFromScenario(nextScenario),
    })
  },
  selectMedium: (mediumId) =>
    set({
      scenario: scenarioForMedium(mediumId),
      activeMediumId: mediumId,
    }),
  updateField: (target, value) =>
    set((state) => ({
      scenario: writeTarget(state.scenario, target, value),
      activeMediumId: state.activeMediumId,
    })),
}))
