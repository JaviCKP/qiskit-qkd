import { expect, test } from 'vitest'

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
