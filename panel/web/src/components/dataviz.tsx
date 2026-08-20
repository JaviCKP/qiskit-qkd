import { useId, type ReactNode } from 'react'

import { formatNumber, percent } from '@/lib/format'
import { chartColor } from '@/lib/palette'

/**
 * Shared chart primitives for the panel.
 *
 * Every mark here is driven by real characterisation numbers coming back from
 * the API — none of these components invent or extrapolate physics, they only
 * lay out values the library already computed.
 *
 * Colour comes from the validated categorical ramp in `index.css`
 * (`--chart-1..6`). Slots are assigned in fixed order and never cycled; the UI
 * accent and the status colours are deliberately outside that ramp so a data
 * series can never be confused with a state.
 */

export type StackSegment = {
  /** Stable identity: colour follows the entity, not its rank in the sorted list. */
  id: string
  label: string
  value: number
  /** Slot index into the categorical ramp. Fixed per entity by the caller. */
  slot: number
  /** Optional longer text shown in the hover tooltip and the table view. */
  detail?: string
}

/**
 * Horizontal stacked bar with a 2px surface gap between fills, per-segment
 * hover tooltips and an always-present legend. Segments whose share is too
 * small to label are still in the legend and the table, so identity never
 * depends on reading a sliver of colour.
 */
export function StackedBar({
  segments,
  total,
  unit = '',
  emptyLabel = 'Sin contribuciones',
  formatValue = (value: number) => formatNumber(value),
}: {
  segments: StackSegment[]
  total?: number
  unit?: string
  emptyLabel?: string
  formatValue?: (value: number) => string
}) {
  const positive = segments.filter((segment) => Number.isFinite(segment.value) && segment.value > 0)
  const sum = total ?? positive.reduce((accumulator, segment) => accumulator + segment.value, 0)

  if (!positive.length || sum <= 0) {
    return (
      <p className="rounded-control border border-dashed border-border px-3 py-4 text-center text-2xs text-slate-500">
        {emptyLabel}
      </p>
    )
  }

  return (
    <div className="space-y-2.5">
      <div className="flex h-7 w-full gap-0.5 overflow-hidden rounded" role="img" aria-label={ariaSummary(positive, sum, unit, formatValue)}>
        {positive.map((segment) => {
          const share = segment.value / sum
          return (
            <div
              className="group relative h-full min-w-0.5 first:rounded-l last:rounded-r"
              key={segment.id}
              style={{ flexGrow: share, flexBasis: 0, backgroundColor: chartColor(segment.slot) }}
              title={`${segment.label}: ${formatValue(segment.value)}${unit ? ` ${unit}` : ''} (${percent(share)})`}
            >
              {share > 0.16 ? (
                <span className="pointer-events-none absolute inset-0 flex items-center justify-center px-1 text-2xs font-medium text-white/95 mix-blend-luminosity">
                  {percent(share)}
                </span>
              ) : null}
            </div>
          )
        })}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1.5">
        {positive.map((segment) => (
          <li className="flex items-center gap-1.5 text-2xs text-slate-400" key={segment.id}>
            <span
              aria-hidden="true"
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: chartColor(segment.slot) }}
            />
            <span className="text-slate-300">{segment.label}</span>
            <span className="font-mono tabular-nums text-slate-500">
              {formatValue(segment.value)}{unit ? ` ${unit}` : ''}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Single-value meter. The fill carries severity and the track is a dim step of
 * the same hue, so the state reads across the whole bar rather than only where
 * it happens to stop.
 */
export function Meter({
  label,
  value,
  max = 1,
  display,
  tone = 'accent',
  hint,
}: {
  label: string
  value: number
  max?: number
  display?: string
  tone?: 'accent' | 'success' | 'warning' | 'danger'
  hint?: string
}) {
  const safeMax = max > 0 ? max : 1
  const ratio = Number.isFinite(value) ? Math.min(1, Math.max(0, value / safeMax)) : 0
  const track = {
    accent: 'bg-cyan/15',
    success: 'bg-success/15',
    warning: 'bg-warning/15',
    danger: 'bg-danger/15',
  }[tone]
  const fill = {
    accent: 'bg-cyan',
    success: 'bg-success',
    warning: 'bg-warning',
    danger: 'bg-danger',
  }[tone]

  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-2xs text-slate-400">{label}</span>
        <span className="shrink-0 font-mono text-2xs tabular-nums text-slate-200">
          {display ?? percent(ratio)}
        </span>
      </div>
      <div
        aria-label={`${label}: ${display ?? percent(ratio)}`}
        aria-valuemax={safeMax}
        aria-valuemin={0}
        aria-valuenow={Number.isFinite(value) ? value : 0}
        className={`mt-1.5 h-1.5 w-full overflow-hidden rounded-full ${track}`}
        role="meter"
      >
        <div className={`h-full rounded-full transition-[width] duration-500 ease-emphasis ${fill}`} style={{ width: `${ratio * 100}%` }} />
      </div>
      {hint ? <p className="mt-1 text-2xs leading-4 text-slate-500">{hint}</p> : null}
    </div>
  )
}

/**
 * Compact metric readout. Uses proportional figures for the value itself (a
 * large `tabular-nums` number looks loose at display sizes) and keeps the
 * label in a text token rather than a series colour.
 */
export function StatTile({
  label,
  value,
  unit,
  tone = 'neutral',
  footnote,
  action,
}: {
  label: string
  value: string
  unit?: string
  tone?: 'neutral' | 'accent' | 'success' | 'warning' | 'danger'
  footnote?: ReactNode
  action?: ReactNode
}) {
  const valueTone = {
    neutral: 'text-white',
    accent: 'text-cyan',
    success: 'text-success',
    warning: 'text-warning',
    danger: 'text-danger',
  }[tone]

  return (
    <div className="min-w-0 rounded-control bg-background/60 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 truncate text-2xs text-slate-400" title={label}>{label}</p>
        {action}
      </div>
      <p className="mt-1.5 flex min-w-0 items-baseline gap-1">
        <span className={`truncate font-mono text-lg font-semibold leading-tight ${valueTone}`} title={value}>
          {value}
        </span>
        {unit ? <span className="shrink-0 text-2xs text-slate-500">{unit}</span> : null}
      </p>
      {footnote ? <p className="mt-1 truncate text-2xs text-slate-500">{footnote}</p> : null}
    </div>
  )
}

/**
 * Small multiples of stacked bars — one row per category. Used for the decoy
 * photon-number statistics, where each intensity gets its own bar and the
 * segments share a fixed slot assignment across rows.
 */
export function StackedBarRows({
  rows,
  legend,
  formatValue = (value: number) => percent(value),
}: {
  rows: Array<{ id: string; label: string; caption?: string; segments: StackSegment[] }>
  legend: Array<{ label: string; slot: number }>
  formatValue?: (value: number) => string
}) {
  const tableId = useId()
  return (
    <div className="space-y-3">
      <ul aria-label="Leyenda" className="flex flex-wrap gap-x-4 gap-y-1.5">
        {legend.map((entry) => (
          <li className="flex items-center gap-1.5 text-2xs text-slate-300" key={entry.label}>
            <span aria-hidden="true" className="h-2 w-2 rounded-sm" style={{ backgroundColor: chartColor(entry.slot) }} />
            {entry.label}
          </li>
        ))}
      </ul>
      <table className="w-full border-separate border-spacing-y-1.5 text-left" id={tableId}>
        <caption className="sr-only">Distribución del número de fotones por intensidad</caption>
        <tbody>
          {rows.map((row) => {
            const sum = row.segments.reduce((accumulator, segment) => accumulator + Math.max(0, segment.value), 0)
            return (
              <tr key={row.id}>
                <th className="w-28 pr-3 align-middle font-normal" scope="row">
                  <span className="block truncate text-2xs font-medium text-slate-200" title={row.label}>{row.label}</span>
                  {row.caption ? <span className="block truncate text-2xs text-slate-500">{row.caption}</span> : null}
                </th>
                <td className="align-middle">
                  <div className="flex h-5 w-full gap-0.5 overflow-hidden rounded">
                    {row.segments.map((segment) => (
                      <div
                        className="h-full min-w-0 first:rounded-l last:rounded-r"
                        key={segment.id}
                        style={{
                          flexGrow: sum > 0 ? Math.max(0, segment.value) / sum : 0,
                          flexBasis: 0,
                          backgroundColor: chartColor(segment.slot),
                        }}
                        title={`${row.label} · ${segment.label}: ${formatValue(segment.value)}`}
                      />
                    ))}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ariaSummary(
  segments: StackSegment[],
  sum: number,
  unit: string,
  formatValue: (value: number) => string,
): string {
  const parts = segments.map(
    (segment) => `${segment.label} ${formatValue(segment.value)}${unit ? ` ${unit}` : ''}`,
  )
  return `Total ${formatValue(sum)}${unit ? ` ${unit}` : ''}. ${parts.join('. ')}.`
}
