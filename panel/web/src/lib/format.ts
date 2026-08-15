import type { JsonObject } from '@/api/client'
import { isRecord } from '@/features/shared/scenarioPaths'

export function formatNumber(value: unknown, suffix = ''): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return '—'
  }
  const absolute = Math.abs(value)
  const formatted = absolute !== 0 && (absolute < 1e-4 || absolute >= 1e6)
    ? value.toExponential(3)
    : value.toFixed(value === 0 ? 0 : absolute < 0.01 ? 6 : 2)
  return `${formatted}${suffix}`
}

export function formatInputValue(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

export function parseInputValue(value: string, type: string): unknown {
  if (value.trim() === '') {
    return null
  }
  if (type === 'integer') {
    return Number.parseInt(value, 10)
  }
  if (type === 'number') {
    return Number(value)
  }
  return value
}

export function metricRecord(summary: JsonObject): JsonObject {
  return isRecord(summary.metrics) ? summary.metrics : summary
}
