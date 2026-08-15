import { expect, test } from 'vitest'

import { cloneJson, isRecord, readTarget, writeTarget } from './scenarioPaths'

test('reads root and nested scenario targets', () => {
  const scenario = {
    pulses: 1024,
    channel: { kind: 'fiber', distance_km: 25 },
  }

  expect(readTarget(scenario, 'scenario.pulses')).toBe(1024)
  expect(readTarget(scenario, 'channel.kind')).toBe('fiber')
  expect(readTarget(scenario, 'channel.distance_km')).toBe(25)
  expect(readTarget(scenario, 'channel.missing')).toBeUndefined()
})

test('writes targets immutably', () => {
  const scenario = {
    pulses: 1024,
    channel: { kind: 'fiber', distance_km: 25 },
  }

  const next = writeTarget(scenario, 'channel.distance_km', 80)

  expect(next).toEqual({
    pulses: 1024,
    channel: { kind: 'fiber', distance_km: 80 },
  })
  expect(scenario.channel.distance_km).toBe(25)
})

test('supports scenario-prefixed root writes', () => {
  const next = writeTarget({ pulses: 1024 }, 'scenario.pulses', 4096)

  expect(next).toEqual({ pulses: 4096 })
})

test('recognizes records and clones JSON-safe values', () => {
  const original = { channel: { kind: 'ideal' }, rows: [1, 2] }
  const cloned = cloneJson(original)

  expect(isRecord(original)).toBe(true)
  expect(isRecord([1, 2])).toBe(false)
  expect(cloned).toEqual(original)
  expect(cloned).not.toBe(original)
  expect(cloned.channel).not.toBe(original.channel)
})
