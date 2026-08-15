import { expect, test } from 'vitest'

import { mediumOptions, scenarioForMedium } from '@/features/lab/mediums'
import { readTarget } from '@/features/shared/scenarioPaths'

import {
  applyCurveScenarioPatch,
  buildCurveRequest,
  curveRecipes,
  describeCurveRequest,
  hasPhysicalDynamicVariation,
  isCurveRequestApplicable,
} from './recipes'

test('builds a fiber distance sweep from a recipe', () => {
  const request = buildCurveRequest('skr-distance', 'fiber')

  expect(request.axis).toEqual({
    target: 'channel.distance_km',
    values: { start: 0, stop: 120, steps: 25, scale: 'linear' },
  })
  expect(request.metric).toBe('secret_key_rate_bps')
  expect(describeCurveRequest(request)).toBe(
    'Barrido de distancia de fibra de 0 a 120 km en 25 puntos.',
  )
})

test('builds an ideal baseline sweep without medium loss controls', () => {
  const request = buildCurveRequest('ideal-baseline', 'ideal')

  expect(request.axis.target).toBe('scenario.pulses')
  expect(request.axis.values).toEqual({ start: 256, stop: 8192, steps: 8, scale: 'log' })
  expect(request.metric).toBe('qber')
})

test('builds recipe-specific medium sweeps', () => {
  expect(buildCurveRequest('gain-pointing', 'satellite').axis.target).toBe(
    'channel.pointing_jitter_rad',
  )
  expect(buildCurveRequest('gain-water-extinction', 'underwater').axis.target).toBe(
    'channel.underwater_extinction_m_inv',
  )
  expect(buildCurveRequest('qber-atmosphere', 'air').axis.target).toBe(
    'channel.atmospheric_extinction_db_km',
  )
})

test('mean photon recipe switches to an effective scalar source', () => {
  const request = buildCurveRequest('mean-photon-number', 'fiber')
  const scenario = applyCurveScenarioPatch(scenarioForMedium('fiber'), request.scenarioPatch)

  expect(request.axis.target).toBe('source.mean_photon_number')
  expect(readTarget(scenario, 'source.kind')).toBe('weak_coherent')
  expect(readTarget(scenario, 'source.decoy_intensities')).toEqual([])
  expect(readTarget(scenario, 'post_processing.decoy_security_estimation_enabled')).toBe(false)
})

test('keeps legacy scenario-root patches compatible', () => {
  const scenario = scenarioForMedium('ideal')
  scenario.pulses = 128
  expect(
    applyCurveScenarioPatch(
      scenario,
      { scenario: { pulses: 256 } },
    ).pulses,
  ).toBe(256)
})

test.each([
  ['vacuum', false],
  ['air', true],
  ['satellite', true],
] as const)('pointing recipe applicability for %s is %s', (mediumId, expected) => {
  const request = buildCurveRequest('gain-pointing', mediumId)

  expect(isCurveRequestApplicable(request, scenarioForMedium(mediumId)).applicable).toBe(expected)
})

test('time applicability requires a genuinely varying physical schedule', () => {
  const withoutSchedules = scenarioForMedium('fiber')
  withoutSchedules.dynamic = { parameter_schedules: [] }
  const constantPreset = scenarioForMedium('fiber')
  const flatRamp = scenarioForMedium('fiber')
  flatRamp.dynamic = {
    parameter_schedules: [
      {
        target: 'channel.fixed_loss_db',
        profile: {
          kind: 'linear',
          start_s: 0,
          end_s: 0.001,
          start_value: 2,
          end_value: 2,
        },
      },
    ],
  }
  const varyingRamp = scenarioForMedium('fiber')
  varyingRamp.dynamic = {
    parameter_schedules: [
      {
        target: 'channel.fixed_loss_db',
        profile: {
          kind: 'linear',
          start_s: 0,
          end_s: 0.001,
          start_value: 0,
          end_value: 8,
        },
      },
    ],
  }

  expect(hasPhysicalDynamicVariation(withoutSchedules, 0, 0.001)).toBe(false)
  expect(hasPhysicalDynamicVariation(constantPreset, 0, 0.001)).toBe(false)
  expect(hasPhysicalDynamicVariation(flatRamp, 0, 0.001)).toBe(false)
  expect(hasPhysicalDynamicVariation(varyingRamp, 0, 0.001)).toBe(true)
})

test('every medium default recipe is physically applicable', () => {
  for (const medium of mediumOptions) {
    const request = buildCurveRequest(medium.defaultCurveRecipeId, medium.id)
    expect(isCurveRequestApplicable(request, medium.scenario).applicable).toBe(true)
  }
})

test('exposes required one-click recipes', () => {
  expect(curveRecipes.map((recipe) => recipe.id)).toContain('qber-eve')
  expect(curveRecipes.map((recipe) => recipe.id)).toContain('chsh-depolarization')
  expect(curveRecipes.map((recipe) => recipe.id)).toContain('metrics-time')
})

test('medium default recipes point to real recipe ids', () => {
  const recipeIds = new Set(curveRecipes.map((recipe) => recipe.id))

  for (const medium of mediumOptions) {
    expect(recipeIds.has(medium.defaultCurveRecipeId)).toBe(true)
  }
})

test('qber eve recipe prepares intercept-resend scenario', () => {
  const request = buildCurveRequest('qber-eve', 'fiber')

  expect(request.axis).toEqual({
    target: 'eavesdropper.intercept_probability',
    values: { start: 0, stop: 1, steps: 11, scale: 'linear' },
  })
  expect(request.scenarioPatch).toEqual({
    protocol: { name: 'bb84' },
    eavesdropper: { kind: 'intercept_resend' },
  })
})

test('chsh recipe prepares e91 scenario', () => {
  const request = buildCurveRequest('chsh-depolarization', 'vacuum')
  const recipe = curveRecipes.find((candidate) => candidate.id === 'chsh-depolarization')

  expect(request.metric).toBe('chsh_s')
  expect(recipe?.question).toContain('CHSH observado')
  expect(request.scenarioPatch).toEqual({
    protocol: { name: 'e91' },
    source: { kind: 'entangled_pair' },
  })
})

test('metrics time recipe uses synthetic time axis', () => {
  const request = buildCurveRequest('metrics-time', 'fiber')

  expect(request.axis).toEqual({
    target: 'time_s',
    values: { start: 0, stop: 0.001, steps: 8, scale: 'linear' },
  })
})

test('describes singular point count cleanly', () => {
  const request = buildCurveRequest('custom-axis', 'custom')
  request.axis = {
    target: 'channel.distance_km',
    values: { start: 0, stop: 1, steps: 1, scale: 'linear' },
  }

  expect(describeCurveRequest(request)).toContain('1 punto.')
})
