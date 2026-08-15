import type { JsonObject } from '@/api/client'

export type CurvePoint = readonly [number, number]

type PlotValue = number | string | boolean | null

/** Accept both legacy summary arrays and the compact columnar sweep DTO. */
export function sweepSummaryRows(value: unknown): JsonObject[] {
  if (Array.isArray(value)) {
    return value.filter(isRecord)
  }
  const rowCountValue = isRecord(value) ? value.row_count : null
  if (!isRecord(value) || value.schema_version !== 2 || typeof rowCountValue !== 'number' || !Number.isInteger(rowCountValue) || rowCountValue < 0 || !isRecord(value.columns)) {
    return []
  }
  const rowCount = rowCountValue
  const rows = Array.from({ length: rowCount }, () => ({} as JsonObject))
  const missing = isRecord(value.missing) ? value.missing : {}
  for (const [key, rawValues] of Object.entries(value.columns)) {
    if (!Array.isArray(rawValues)) continue
    const omitted = Array.isArray(missing[key]) ? new Set(missing[key].filter((item): item is number => Number.isInteger(item))) : new Set<number>()
    rawValues.slice(0, rowCount).forEach((item, index) => {
      if (!omitted.has(index)) rows[index][key] = item
    })
  }
  return rows
}

export function finiteCurvePoints(
  rows: Array<Record<string, unknown>>,
  xKey: string,
  yKey: string,
): CurvePoint[] {
  return curvePointSegments(rows, xKey, yKey).flat()
}

export function curvePointSegments(
  rows: Array<Record<string, unknown>>,
  xKey: string,
  yKey: string,
): CurvePoint[][] {
  const segments: CurvePoint[][] = []
  let current: CurvePoint[] = []

  for (const row of rows) {
    const x = finiteNumber(row[xKey])
    const y = finiteNumber(row[yKey])
    if (x === null || y === null) {
      if (current.length > 0) {
        segments.push(current)
        current = []
      }
      continue
    }
    current.push([x, y])
  }
  if (current.length > 0) {
    segments.push(current)
  }
  return segments
}

export function curveTraces(
  rows: Array<Record<string, unknown>>,
  xKey: string,
  metric: string,
  seriesKey: string,
  metricName = metric,
): Array<Record<string, unknown>> {
  const groups = new Map<string, Array<Record<string, unknown>>>()
  for (const row of rows) {
    const group = seriesKey ? String(row[seriesKey] ?? 'serie') : metricName
    groups.set(group, [...(groups.get(group) ?? []), row])
  }

  const colors = ['#22d3ee', '#34d399', '#fbbf24', '#8b5cf6', '#f87171', '#e5e7eb']
  return Array.from(groups.entries()).flatMap(([name, groupRows], index) => {
    const color = colors[index % colors.length]
    const meanKey = `${metric}_mean`
    const p05Key = `${metric}_p05`
    const p95Key = `${metric}_p95`
    const yKey = meanKey in (groupRows[0] ?? {}) ? meanKey : metric
    const x = groupRows.map((row) => plotValue(row[xKey]))
    const line = {
      x,
      y: groupRows.map((row) => finiteNumber(row[yKey])),
      connectgaps: false,
      mode: 'lines+markers',
      name,
      type: 'scatter',
      marker: { color },
      line: { color },
    }
    if (!(p05Key in (groupRows[0] ?? {})) || !(p95Key in (groupRows[0] ?? {}))) {
      return [line]
    }
    return [
      {
        x,
        y: groupRows.map((row) => finiteNumber(row[p95Key])),
        connectgaps: false,
        hoverinfo: 'skip',
        line: { color: 'transparent' },
        name: `${name} p95`,
        showlegend: false,
        type: 'scatter',
      },
      {
        x,
        y: groupRows.map((row) => finiteNumber(row[p05Key])),
        connectgaps: false,
        fill: 'tonexty',
        fillcolor: `${color}33`,
        hoverinfo: 'skip',
        line: { color: 'transparent' },
        name: `${name} p05`,
        showlegend: false,
        type: 'scatter',
      },
      line,
    ]
  })
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function plotValue(value: unknown): PlotValue {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  return typeof value === 'string' || typeof value === 'boolean' ? value : null
}

function isRecord(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
