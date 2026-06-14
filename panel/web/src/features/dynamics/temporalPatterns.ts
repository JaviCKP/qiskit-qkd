export type TemporalPatternId = 'stable' | 'degradation' | 'recovery' | 'drift' | 'burst'
export type TemporalPhenomenon = 'loss' | 'error' | 'alignment' | 'background' | 'timing' | 'eve'
export type TemporalSeverity = 'mild' | 'moderate' | 'severe'
export type TemporalDuration = 'short' | 'medium' | 'long'
export type TemporalDirection = 'increasing' | 'decreasing' | 'spike'

export type TemporalPatternRequest = {
  pattern: TemporalPatternId
  phenomenon: TemporalPhenomenon
  severity: TemporalSeverity
  duration: TemporalDuration
  direction: TemporalDirection
  currentValue: number
}

export type TemporalSchedule = {
  target: string
  profile:
    | { kind: 'constant'; start_s: number; end_s: number; value: number }
    | {
        kind: 'linear'
        start_s: number
        end_s: number
        start_value: number
        end_value: number
      }
}

export const temporalPatternOptions = [
  { id: 'stable' as const, label: 'Stable link' },
  { id: 'degradation' as const, label: 'Gradual degradation' },
  { id: 'recovery' as const, label: 'Recovery' },
  { id: 'drift' as const, label: 'Drift' },
  { id: 'burst' as const, label: 'Noise burst' },
]

const targets: Record<TemporalPhenomenon, string> = {
  loss: 'channel.fixed_loss_db',
  error: 'channel.depolarizing_probability',
  alignment: 'channel.polarization_rotation_y_rad',
  background: 'channel.background_count_rate_hz',
  timing: 'timing.clock_offset_s',
  eve: 'eavesdropper.intercept_probability',
}

const durations: Record<TemporalDuration, number> = {
  short: 0.001,
  medium: 0.01,
  long: 0.1,
}

const deltas: Record<TemporalPhenomenon, Record<TemporalSeverity, number>> = {
  loss: { mild: 1, moderate: 3, severe: 8 },
  error: { mild: 0.01, moderate: 0.05, severe: 0.1 },
  alignment: { mild: 0.01, moderate: 0.05, severe: 0.1 },
  background: { mild: 50, moderate: 200, severe: 500 },
  timing: { mild: 1e-10, moderate: 5e-10, severe: 1e-9 },
  eve: { mild: 0.05, moderate: 0.2, severe: 0.5 },
}

const recoveryDeltaMultiplier = 0.5

export function buildTemporalSchedule(
  request: TemporalPatternRequest,
): TemporalSchedule {
  const target = targets[request.phenomenon]
  const duration = durations[request.duration]
  const currentValue = clampValue(request.phenomenon, request.currentValue)
  const delta = deltas[request.phenomenon][request.severity]

  if (request.pattern === 'stable') {
    return {
      target,
      profile: {
        kind: 'constant',
        start_s: 0,
        end_s: duration,
        value: currentValue,
      },
    }
  }

  if (request.pattern === 'burst') {
    return {
      target,
      profile: {
        kind: 'constant',
        start_s: roundNumber(duration / 4),
        end_s: roundNumber(duration / 2),
        value: clampValue(request.phenomenon, currentValue + delta),
      },
    }
  }

  const deltaMultiplier =
    request.pattern === 'recovery' ? recoveryDeltaMultiplier : 1
  const endValue =
    currentValue + directionSign(request.pattern, request.direction) * delta * deltaMultiplier

  return {
    target,
    profile: {
      kind: 'linear',
      start_s: 0,
      end_s: duration,
      start_value: currentValue,
      end_value: clampValue(request.phenomenon, endValue),
    },
  }
}

export function describeTemporalSchedule(schedule: TemporalSchedule): string {
  if (schedule.profile.kind === 'constant') {
    return `${schedule.target} holds ${schedule.profile.value} from ${schedule.profile.start_s}s to ${schedule.profile.end_s}s.`
  }

  return `${schedule.target} moves from ${schedule.profile.start_value} to ${schedule.profile.end_value} from ${schedule.profile.start_s}s to ${schedule.profile.end_s}s.`
}

function directionSign(
  pattern: TemporalPatternId,
  direction: TemporalDirection,
): 1 | -1 {
  if (direction === 'spike' && pattern !== 'burst') {
    throw new Error('spike direction only applies to burst patterns')
  }

  if (pattern === 'recovery' || direction === 'decreasing') {
    return -1
  }
  return 1
}

function clampValue(phenomenon: TemporalPhenomenon, value: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }

  if (phenomenon === 'error' || phenomenon === 'eve') {
    return roundNumber(Math.min(1, Math.max(0, value)))
  }

  if (phenomenon === 'alignment' || phenomenon === 'timing') {
    return roundNumber(value)
  }

  return roundNumber(Math.max(0, value))
}

function roundNumber(value: number): number {
  return Number(value.toPrecision(12))
}
