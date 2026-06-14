import { beforeEach, expect, test } from 'vitest'

import { useDesignerStore } from './scenarioStore'

beforeEach(() => {
  useDesignerStore.setState(useDesignerStore.getInitialState(), true)
})

test('loads a scenario and infers the active medium', () => {
  useDesignerStore.getState().loadScenario({
    schema_version: 1,
    channel: { kind: 'underwater' },
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
    schema_version: 1,
    channel: { kind: 'fiber', distance_km: 25 },
    metadata: {},
  }

  useDesignerStore.getState().loadScenario(external)
  external.channel.distance_km = 90

  expect(useDesignerStore.getState().scenario.channel).toMatchObject({ distance_km: 25 })
})
