import { expect, test } from 'vitest'

import { curvePointSegments, curveTraces, finiteCurvePoints, sweepSummaryRows } from './curveData'

test('preserves null curve samples as plot gaps while retaining genuine zeroes', () => {
  const rows = [
    { distance: 0, qber: 0.02 },
    { distance: 10, qber: null },
    { distance: 20, qber: 0 },
  ]

  const [trace] = curveTraces(rows, 'distance', 'qber', '')

  expect(trace.x).toEqual([0, 10, 20])
  expect(trace.y).toEqual([0.02, null, 0])
  expect(trace.connectgaps).toBe(false)
  expect(finiteCurvePoints(rows, 'distance', 'qber')).toEqual([
    [0, 0.02],
    [20, 0],
  ])
  expect(curvePointSegments(rows, 'distance', 'qber')).toEqual([
    [[0, 0.02]],
    [[20, 0]],
  ])
})

test('does not coerce missing axes or metrics to zero', () => {
  const [trace] = curveTraces([{ x: null }, { x: 0, y: undefined }], 'x', 'y', '')

  expect(trace.x).toEqual([null, 0])
  expect(trace.y).toEqual([null, null])
  expect(finiteCurvePoints([{ x: null, y: 2 }], 'x', 'y')).toEqual([])
})

test('expands compact columnar sweep summaries and keeps legacy arrays', () => {
  const compact = {
    schema_version: 2,
    row_count: 2,
    columns: {
      distance_km: [0, 10],
      qber_mean: [0.1, null],
    },
    missing: { qber_mean: [1] },
  }

  expect(sweepSummaryRows(compact)).toEqual([
    { distance_km: 0, qber_mean: 0.1 },
    { distance_km: 10 },
  ])
  expect(sweepSummaryRows([{ distance_km: 1 }])).toEqual([{ distance_km: 1 }])
})
