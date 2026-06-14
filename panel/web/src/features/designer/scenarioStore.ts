import { create } from 'zustand'

import type { ScenarioPayload } from '@/api/client'
import { defaultScenario } from './defaultScenario'

type DesignerState = {
  scenario: ScenarioPayload
  loadScenario: (scenario: ScenarioPayload) => void
  updateField: (target: string, value: unknown) => void
}

export const useDesignerStore = create<DesignerState>((set) => ({
  scenario: defaultScenario,
  loadScenario: (scenario) => set({ scenario }),
  updateField: (target, value) =>
    set((state) => ({ scenario: updateScenario(state.scenario, target, value) })),
}))

function updateScenario(
  scenario: ScenarioPayload,
  target: string,
  value: unknown,
): ScenarioPayload {
  const [section, field] = target.split('.')
  if (section === 'scenario') {
    return { ...scenario, [field]: value }
  }
  const sectionValue = scenario[section]
  if (!isRecord(sectionValue)) {
    return scenario
  }
  return {
    ...scenario,
    [section]: {
      ...sectionValue,
      [field]: value,
    },
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
