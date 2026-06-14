import { expect, test } from 'vitest'

import { mediumOptions } from '@/features/lab/mediums'

import { buildCurveRequest, curveRecipes, describeCurveRequest } from './recipes'

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
    eavesdropper: { kind: 'intercept_resend' },
  })
})

test('chsh recipe prepares e91 scenario', () => {
  const request = buildCurveRequest('chsh-depolarization', 'vacuum')

  expect(request.metric).toBe('chsh_s')
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
