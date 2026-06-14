import { expect, test } from 'vitest'

import { buildTemporalSchedule, temporalPatternOptions } from './temporalPatterns'

test('builds a stable-link constant schedule', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'stable',
    phenomenon: 'loss',
    severity: 'mild',
    duration: 'short',
    direction: 'increasing',
    currentValue: 2,
  })

  expect(schedule).toEqual({
    target: 'channel.fixed_loss_db',
    profile: { kind: 'constant', start_s: 0, end_s: 0.001, value: 2 },
  })
})

test('builds gradual QBER-driving degradation', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'degradation',
    phenomenon: 'error',
    severity: 'moderate',
    duration: 'medium',
    direction: 'increasing',
    currentValue: 0.01,
  })

  expect(schedule.target).toBe('channel.depolarizing_probability')
  expect(schedule.profile).toEqual({
    kind: 'linear',
    start_s: 0,
    end_s: 0.01,
    start_value: 0.01,
    end_value: 0.06,
  })
})

test('builds recovery by decreasing the selected phenomenon', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'recovery',
    phenomenon: 'background',
    severity: 'severe',
    duration: 'long',
    direction: 'decreasing',
    currentValue: 500,
  })

  expect(schedule.target).toBe('channel.background_count_rate_hz')
  expect(schedule.profile).toEqual({
    kind: 'linear',
    start_s: 0,
    end_s: 0.1,
    start_value: 500,
    end_value: 250,
  })
})

test('builds burst as a finite constant spike', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'burst',
    phenomenon: 'timing',
    severity: 'mild',
    duration: 'short',
    direction: 'spike',
    currentValue: 0,
  })

  expect(schedule.target).toBe('timing.clock_offset_s')
  expect(schedule.profile).toEqual({
    kind: 'constant',
    start_s: 0.00025,
    end_s: 0.0005,
    value: 1e-10,
  })
})

test('allows signed timing offsets when decreasing', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'drift',
    phenomenon: 'timing',
    severity: 'mild',
    duration: 'short',
    direction: 'decreasing',
    currentValue: 0,
  })

  expect(schedule).toEqual({
    target: 'timing.clock_offset_s',
    profile: {
      kind: 'linear',
      start_s: 0,
      end_s: 0.001,
      start_value: 0,
      end_value: -1e-10,
    },
  })
})

test('allows signed alignment drift', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'drift',
    phenomenon: 'alignment',
    severity: 'moderate',
    duration: 'medium',
    direction: 'decreasing',
    currentValue: 0.01,
  })

  expect(schedule.profile).toEqual({
    kind: 'linear',
    start_s: 0,
    end_s: 0.01,
    start_value: 0.01,
    end_value: -0.04,
  })
})

test('clamps probability phenomena but not signed phenomena', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'degradation',
    phenomenon: 'error',
    severity: 'severe',
    duration: 'long',
    direction: 'increasing',
    currentValue: 0.95,
  })

  expect(schedule.profile).toMatchObject({ end_value: 1 })
})

test('rejects spike direction for linear temporal patterns', () => {
  expect(() =>
    buildTemporalSchedule({
      pattern: 'degradation',
      phenomenon: 'error',
      severity: 'mild',
      duration: 'short',
      direction: 'spike',
      currentValue: 0,
    }),
  ).toThrow('spike direction only applies to burst patterns')
})

test('exposes the required named patterns', () => {
  expect(temporalPatternOptions.map((item) => item.id)).toEqual([
    'stable',
    'degradation',
    'recovery',
    'drift',
    'burst',
  ])
})
