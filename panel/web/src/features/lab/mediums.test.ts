import { expect, test } from 'vitest'

import {
  inferMediumFromScenario,
  mediumDefinitions,
  mediumOptions,
  scenarioForMedium,
} from './mediums'

test('exposes all approved medium choices in display order', () => {
  expect(mediumOptions.map((medium) => medium.id)).toEqual([
    'ideal',
    'fiber',
    'vacuum',
    'air',
    'satellite',
    'underwater',
    'custom',
  ])
})

test('builds realistic medium scenarios without sharing object references', () => {
  const fiber = scenarioForMedium('fiber')
  const secondFiber = scenarioForMedium('fiber')

  expect(fiber.channel).toMatchObject({
    kind: 'fiber',
    distance_km: 100,
    attenuation_db_km: 0.2,
    wavelength_nm: 1550,
  })
  expect(fiber.detector).toMatchObject({
    kind: 'threshold',
    efficiency: 0.85,
    dark_count_rate_hz: 10,
  })
  expect(fiber.source).toMatchObject({ kind: 'decoy_weak_coherent' })
  expect(fiber.metadata).toMatchObject({ mediumId: 'fiber' })
  expect(secondFiber).not.toBe(fiber)
  expect(secondFiber.channel).not.toBe(fiber.channel)
})

test('keeps ideal channel clean and quick', () => {
  const ideal = scenarioForMedium('ideal')

  expect(ideal.channel).toMatchObject({
    kind: 'ideal',
    distance_km: 0,
    attenuation_db_km: 0,
    background_count_rate_hz: 0,
  })
  expect(ideal.pulses).toBe(1024)
  expect(ideal.metadata).toMatchObject({ mediumId: 'ideal' })
})

test('infers medium from metadata before channel kind', () => {
  expect(
    inferMediumFromScenario({
      metadata: { mediumId: 'satellite' },
      channel: { kind: 'free_space' },
    }),
  ).toBe('satellite')
})

test('infers medium from channel kind when metadata is absent', () => {
  expect(inferMediumFromScenario({ channel: { kind: 'ideal' } })).toBe('ideal')
  expect(inferMediumFromScenario({ channel: { kind: 'fiber' } })).toBe('fiber')
  expect(inferMediumFromScenario({ channel: { kind: 'underwater' } })).toBe('underwater')
  expect(inferMediumFromScenario({ channel: { kind: 'free_space' } })).toBe('air')
  expect(inferMediumFromScenario({ channel: { kind: 'satellite' } })).toBe('satellite')
  expect(inferMediumFromScenario({ channel: { kind: 'space' } })).toBe('vacuum')
})

test('medium definitions include card copy and default curve recipes', () => {
  for (const medium of mediumOptions) {
    expect(mediumDefinitions[medium.id].label).toBeTruthy()
    expect(mediumDefinitions[medium.id].summary).toBeTruthy()
    expect(mediumDefinitions[medium.id].defaultCurveRecipeId).toBeTruthy()
  }
})
