import { memo, useMemo, useState } from 'react'

import { seriesStyle } from '@/lib/palette'

export type CurvePlotTrace = {
  x?: unknown[]
  y?: unknown[]
  name?: string
  type?: string
  mode?: string
  showlegend?: boolean
  line?: { color?: string; width?: number; dash?: string }
  marker?: { color?: string; size?: number; symbol?: string }
  fill?: string
  fillcolor?: string
}

export type CurvePlotProps = {
  traces: CurvePlotTrace[]
  title: string
  xLabel: string
  yLabel: string
  threshold?: number | null
  thresholdLabel?: string
  className?: string
}

/**
 * Small dependency-free scatter renderer.  Plotly's full bundle is ~4.6 MB
 * for this one chart; the SVG renderer keeps the existing exports and gives
 * us native keyboard/hover semantics through buttons, titles and labels.
 */
export const CurvePlot = memo(function CurvePlot({ traces, title, xLabel, yLabel, threshold = null, thresholdLabel = 'Umbral', className }: CurvePlotProps) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set())
  const model = useMemo(() => buildModel(traces, threshold), [threshold, traces])
  const legend = model.legend
  const toggle = (name: string) => setHidden((current) => {
    const next = new Set(current)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    return next
  })

  return (
    <div className={className ?? 'h-full w-full'} data-testid="curve-plot">
      <div className="sr-only" aria-live="polite">{title}. Eje X: {xLabel}. Eje Y: {yLabel}.</div>
      <svg aria-label={title} className="h-full w-full" role="img" viewBox="0 0 960 414" xmlns="http://www.w3.org/2000/svg">
        <title>{title}</title>
        <desc>Gráfica de dispersión con leyenda interactiva. {xLabel} frente a {yLabel}.</desc>
        <rect fill="#0b1119" height="414" rx="10" width="960" />
        {/* Recessive grid: horizontal rules only, so the marks stay dominant. */}
        <g aria-hidden="true" fill="none" stroke="#243141" strokeWidth="1">
          {model.yTicks.map((tick) => <line key={`y-grid-${tick.value}`} x1={model.left} x2={model.right} y1={tick.position} y2={tick.position} />)}
        </g>
        <g aria-hidden="true" fill="none" stroke="#3a4a5a" strokeWidth="1">
          <line x1={model.left} x2={model.left} y1={model.top} y2={model.bottom} />
          <line x1={model.left} x2={model.right} y1={model.bottom} y2={model.bottom} />
        </g>
        <g fill="#94a3b8" fontSize="12" textAnchor="end">
          {model.yTicks.map((tick) => <text key={`y-label-${tick.value}`} x={model.left - 8} y={tick.position + 4}>{formatTick(tick.value)}</text>)}
        </g>
        <g fill="#94a3b8" fontSize="12" textAnchor="middle">
          {model.xTicks.map((tick) => <text key={`x-label-${tick.value}`} x={tick.position} y={model.bottom + 18}>{formatTick(tick.value)}</text>)}
        </g>
        <text fill="#94a3b8" fontSize="12" textAnchor="middle" x={(model.left + model.right) / 2} y="407">{xLabel}</text>
        <text fill="#94a3b8" fontSize="12" textAnchor="middle" transform={`translate(15 ${(model.top + model.bottom) / 2}) rotate(-90)`}>{yLabel}</text>
        {threshold !== null && model.yScale(threshold) !== null ? <g><line stroke="#e3ae49" strokeDasharray="4 4" strokeWidth="1.5" x1={model.left} x2={model.right} y1={model.yScale(threshold) ?? 0} y2={model.yScale(threshold) ?? 0} /><text fill="#e3ae49" fontSize="12" x={model.right - 4} y={(model.yScale(threshold) ?? 0) - 5} textAnchor="end">{thresholdLabel}</text></g> : null}
        {model.series.map((series) => {
          if (series.visibilityName && hidden.has(series.visibilityName)) return null
          return <g key={series.key}>{series.fillPaths.map((path, index) => <path d={path} fill={series.fill ?? 'none'} key={`${series.key}-fill-${index}`} stroke="none" />)}{series.paths.map((path, index) => <path d={path} fill="none" key={`${series.key}-line-${index}`} stroke={series.stroke} strokeDasharray={series.dash} strokeWidth={series.width} />)}{series.showMarkers ? series.points.map((point, index) => <circle aria-label={`${series.name ?? 'serie'} ${formatTick(point.rawX)}, ${formatTick(point.rawY)}`} className="transition-[r] duration-150 hover:[r:6]" fill={series.markerColor} key={`${series.key}-${index}`} r={series.radius} stroke="#0b1119" strokeWidth="2" tabIndex={0} cx={point.x} cy={point.y}><title>{`${series.name ?? 'serie'}: ${formatTick(point.rawX)}, ${formatTick(point.rawY)}`}</title></circle>) : null}</g>
        })}
      </svg>
      <div aria-label="Leyenda de la gráfica" className="mt-2 flex flex-wrap gap-1" role="group">
        {legend.map((entry) => {
          const visible = !hidden.has(entry.name)
          return (
            <button
              aria-pressed={visible}
              className={`flex items-center gap-1.5 rounded-control border px-2.5 py-1.5 text-xs transition-colors ${
                visible
                  ? 'border-border bg-raised text-slate-200 hover:border-border-strong'
                  : 'border-transparent text-slate-500 line-through hover:bg-white/5'
              }`}
              key={entry.name}
              onClick={() => toggle(entry.name)}
              title={visible ? `Ocultar ${entry.name}` : `Mostrar ${entry.name}`}
              type="button"
            >
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ backgroundColor: visible ? entry.color : 'transparent', boxShadow: `inset 0 0 0 2px ${entry.color}` }}
              />
              {entry.name}
            </button>
          )
        })}
      </div>
    </div>
  )
})

type Point = { x: number; y: number; rawX: unknown; rawY: unknown }
type Series = {
  key: string
  name: string
  visibilityName: string
  stroke: string
  markerColor: string
  width: number
  radius: number
  dash?: string
  fill?: string
  paths: string[]
  fillPaths: string[]
  points: Point[]
  showMarkers: boolean
}
type PlotModel = {
  left: number
  right: number
  top: number
  bottom: number
  xTicks: Array<{ value: unknown; position: number }>
  yTicks: Array<{ value: number; position: number }>
  series: Series[]
  legend: Array<{ name: string; color: string }>
  yScale: (value: number) => number | null
}

function buildModel(traces: CurvePlotTrace[], threshold: number | null): PlotModel {
  const left = 72
  const right = 936
  const top = 28
  const bottom = 366
  const source = traces.map((trace, index) => ({ trace, index, name: trace.name ?? `Serie ${index + 1}` }))
  const rawPoints = source.map(({ trace }) => toRawPoints(trace)).flat()
  const xNumbers = rawPoints.map((point) => point.x).filter(isFiniteNumber)
  const yNumbers = rawPoints.map((point) => point.y).filter(isFiniteNumber)
  const xMin = xNumbers.length ? Math.min(...xNumbers) : 0
  const categoricalWidth = Math.max(1, ...source.map(({ trace }) => Math.max(0, (trace.y?.length ?? 0) - 1)))
  const xMax = xNumbers.length ? Math.max(...xNumbers) : categoricalWidth
  const yMin = Math.min(0, ...(yNumbers.length ? yNumbers : [0]))
  const yMax = Math.max(1, ...(yNumbers.length ? yNumbers : [1]), ...(threshold === null ? [] : [threshold]))
  const xScale = (value: number) => left + ((value - xMin) / Math.max(1e-12, xMax - xMin)) * (right - left)
  const yScale = (value: number) => Number.isFinite(value) ? bottom - ((value - yMin) / Math.max(1e-12, yMax - yMin)) * (bottom - top) : null
  const series: Series[] = []
  const legend: Array<{ name: string; color: string }> = []
  let previousScaled: Array<Point | null> = []
  source.forEach(({ trace, index, name }) => {
    const fallbackColor = seriesStyle(index).color
    const stroke = trace.line?.color ?? trace.marker?.color ?? fallbackColor
    const markerColor = trace.marker?.color ?? (stroke === 'transparent' ? fallbackColor : stroke)
    const scaled = toRawPoints(trace).map((point, pointIndex): Point | null => {
      const rawX = point.x
      const x = isFiniteNumber(point.x) ? point.x : pointIndex
      const y = isFiniteNumber(point.y) ? point.y : null
      return y === null ? null : { x: xScale(x), y: yScale(y) ?? bottom, rawX, rawY: point.y }
    })
    const points = scaled.filter((point): point is Point => point !== null)
    series.push({
      key: `${name}-${index}`,
      name,
      visibilityName: name.replace(/ p(?:05|95)$/u, ''),
      stroke,
      markerColor,
      width: trace.line?.width ?? 2,
      // >=8px marks stay clickable and visible against the grid.
      radius: trace.marker?.size ? Math.max(4, Math.min(7, trace.marker.size / 2)) : 4,
      dash: dashPattern(trace.line?.dash),
      fill: trace.fillcolor,
      paths: contiguousPaths(scaled),
      fillPaths: trace.fill === 'tonexty' ? bandPaths(scaled, previousScaled) : [],
      points,
      showMarkers: trace.showlegend !== false && (trace.mode === undefined || trace.mode.includes('markers') || Boolean(trace.marker)),
    })
    if (trace.showlegend !== false) legend.push({ name, color: markerColor })
    previousScaled = scaled
  })
  const categoricalValues = source[0]?.trace.x ?? []
  const xTicks = xNumbers.length
    ? [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
        const value = xMin + fraction * (xMax - xMin)
        return { value, position: xScale(value) }
      })
    : sampledCategoryTicks(categoricalValues, xScale)
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
    const value = yMin + fraction * (yMax - yMin)
    return { value, position: yScale(value) ?? bottom }
  })
  return { left, right, top, bottom, xTicks, yTicks, series, legend: dedupeLegend(legend), yScale }
}

function sampledCategoryTicks(values: unknown[], scale: (value: number) => number): Array<{ value: unknown; position: number }> {
  if (!values.length) return [{ value: 0, position: scale(0) }]
  const indexes = Array.from(new Set([0, Math.round((values.length - 1) * 0.25), Math.round((values.length - 1) * 0.5), Math.round((values.length - 1) * 0.75), values.length - 1]))
  return indexes.map((index) => ({ value: values[index], position: scale(index) }))
}

function contiguousPaths(points: Array<Point | null>): string[] {
  const paths: string[] = []
  let segment: Point[] = []
  const flush = () => {
    if (segment.length > 1) paths.push(pointPath(segment))
    segment = []
  }
  points.forEach((point) => {
    if (point === null) flush()
    else segment.push(point)
  })
  flush()
  return paths
}

function bandPaths(current: Array<Point | null>, previous: Array<Point | null>): string[] {
  const paths: string[] = []
  let lower: Point[] = []
  let upper: Point[] = []
  const flush = () => {
    if (lower.length > 1 && upper.length === lower.length) {
      paths.push(`${pointPath(lower)} ${upper.slice().reverse().map((point) => `L${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')} Z`)
    }
    lower = []
    upper = []
  }
  for (let index = 0; index < Math.max(current.length, previous.length); index += 1) {
    const currentPoint = current[index]
    const previousPoint = previous[index]
    if (!currentPoint || !previousPoint) flush()
    else {
      lower.push(currentPoint)
      upper.push(previousPoint)
    }
  }
  flush()
  return paths
}

function pointPath(points: Point[]): string {
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'}${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
}

function dashPattern(value: string | undefined): string | undefined {
  if (value === 'dash') return '8 5'
  if (value === 'dot') return '2 4'
  if (value === 'dashdot') return '8 4 2 4'
  return undefined
}

function toRawPoints(trace: CurvePlotTrace): Array<{ x: unknown; y: unknown }> {
  const x = trace.x ?? []
  const y = trace.y ?? []
  return y.map((value, index) => ({ x: x[index] ?? index, y: value }))
}

function dedupeLegend(entries: Array<{ name: string; color: string }>): Array<{ name: string; color: string }> {
  const seen = new Set<string>()
  return entries.filter((entry) => !seen.has(entry.name) && (seen.add(entry.name), true))
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function formatTick(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('es-ES', { maximumFractionDigits: 4 }) : String(value ?? '—')
}
