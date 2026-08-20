import { expect, test } from 'vitest'

import { decoyPhotonRows, lossBudget } from './linkBudget'

/** Fibre run: the whole loss is the medium's own attenuation. */
const fiberChannel = {
  loss_db: 5,
  transmittance: 0.3162277660168379,
  geometric_transmittance: 1,
  atmospheric_loss_db: 0,
  fixed_loss_db: 0,
  polarization_dependent_loss_db: 0,
  attenuation_db_km: 0.2,
  distance_km: 25,
}

/** Free-space run: geometry and extinction dominate and `attenuation_db_km`
 *  is reported but NOT applied by the library for this channel kind. */
const satelliteChannel = {
  loss_db: 26.151403521958727,
  geometric_transmittance: 0.03844675124951943,
  atmospheric_loss_db: 10,
  fixed_loss_db: 2,
  polarization_dependent_loss_db: 0,
  attenuation_db_km: 0.2,
  distance_km: 500,
}

const sumOf = (segments: Array<{ value: number }>) =>
  segments.reduce((total, segment) => total + segment.value, 0)

test('attributes an unexplained fibre loss to the medium attenuation', () => {
  const segments = lossBudget(fiberChannel)

  expect(segments).toHaveLength(1)
  expect(segments[0]).toMatchObject({ id: 'medium', value: 5 })
})

test('splits a free-space loss into the reported geometric and extinction terms', () => {
  const segments = lossBudget(satelliteChannel)
  const byId = Object.fromEntries(segments.map((segment) => [segment.id, segment.value]))

  expect(byId.geometric).toBeCloseTo(14.1514, 3)
  expect(byId.atmospheric).toBe(10)
  expect(byId.fixed).toBe(2)
  // `attenuation_db_km * distance_km` would be 100 dB here; attributing it
  // would quadruple the bar. The residual must stay at zero instead.
  expect(byId.medium).toBeUndefined()
})

test('always sums to the loss the library reported', () => {
  for (const channel of [fiberChannel, satelliteChannel]) {
    expect(sumOf(lossBudget(channel))).toBeCloseTo(channel.loss_db, 9)
  }
})

test('falls back to a single opaque bar when the parts exceed the total', () => {
  const segments = lossBudget({ ...satelliteChannel, loss_db: 3 })

  expect(segments).toEqual([{ id: 'total', label: 'Pérdida del canal', value: 3, slot: 0 }])
})

test('reports no segments for a lossless or uncharacterised channel', () => {
  expect(lossBudget({ loss_db: 0 })).toEqual([])
  expect(lossBudget({})).toEqual([])
})

test('builds one photon-statistics row per decoy intensity', () => {
  const rows = decoyPhotonRows({
    decoy_probabilities: [
      { name: 'signal', mean_photon_number: 0.5, selection_probability: 0.8, p_zero: 0.6065, p_one: 0.3033, p_multi: 0.0902 },
      { name: 'vacuum', mean_photon_number: 0, selection_probability: 0.2, p_zero: 1, p_one: 0, p_multi: 0 },
    ],
  })

  expect(rows).toHaveLength(2)
  expect(rows?.[0].label).toBe('Señal')
  expect(rows?.[0].caption).toContain('80 %')
  expect(rows?.[0].segments.map((segment) => segment.slot)).toEqual([5, 0, 1])
  // Slots are fixed per photon count, so the colour of "1 fotón" is the same
  // in every row regardless of how the values happen to sort.
  expect(rows?.[1].segments.map((segment) => segment.slot)).toEqual([5, 0, 1])
})

test('reports no photon rows for sources without decoy intensities', () => {
  expect(decoyPhotonRows({})).toBeNull()
  expect(decoyPhotonRows({ decoy_probabilities: [] })).toBeNull()
})
