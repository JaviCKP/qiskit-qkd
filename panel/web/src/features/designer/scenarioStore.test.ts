import { expect, test } from 'vitest'

import { useDesignerStore } from './scenarioStore'

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
