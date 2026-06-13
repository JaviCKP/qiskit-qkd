import {
  QueryClient,
  QueryClientProvider,
  useQueries,
  useQuery,
} from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { ComponentType } from 'react'
import type { PlotParams } from 'react-plotly.js'
import {
  Activity,
  CheckCircle2,
  FlaskConical,
  Gauge,
  Library,
  Plus,
  RadioTower,
  Trash2,
} from 'lucide-react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponentModule from 'react-plotly.js/factory'

import {
  ApiError,
  characterize,
  fetchCatalog,
  type ApiValidationIssue,
  type CatalogField,
  type CatalogSection,
  validateScenario,
  previewDynamics,
} from './api/client'
import { fetchHealthStatus } from './api/health'
import { useDesignerStore } from './features/designer/scenarioStore'
import { qkdPlotlyLayout } from './lib/plotlyTemplate'

const queryClient = new QueryClient()
type PlotComponentFactory = (plotly: object) => ComponentType<PlotParams>
const createPlotlyComponent = resolveDefaultExport<PlotComponentFactory>(
  createPlotlyComponentModule,
)
const Plot = createPlotlyComponent(Plotly)

function resolveDefaultExport<T>(module: T | { default: T }): T {
  if (typeof module === 'object' && module !== null && 'default' in module) {
    return (module as { default: T }).default
  }
  return module as T
}

function PanelShell() {
  const scenario = useDesignerStore((state) => state.scenario)
  const updateField = useDesignerStore((state) => state.updateField)
  const debouncedScenario = useDebouncedValue(scenario, 250)
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealthStatus,
    retry: false,
  })
  const catalog = useQuery({
    queryKey: ['catalog'],
    queryFn: fetchCatalog,
  })
  const validation = useQuery({
    queryKey: ['scenario-validation', debouncedScenario],
    queryFn: () => validateScenario(debouncedScenario),
  })
  const states = useQueries({
    queries: (['source', 'channel', 'detector', 'timing'] as const).map((section) => ({
      queryKey: ['characterize', section, debouncedScenario],
      queryFn: () => characterize(section, debouncedScenario),
    })),
  })
  const dynamics = useQuery({
    queryKey: ['dynamics-preview', debouncedScenario],
    queryFn: () => previewDynamics(debouncedScenario),
  })

  const validationIssues = validation.error instanceof ApiError ? validation.error.issues : []
  const catalogSections = catalog.data?.sections ?? []
  const sweepableFields = catalogSections.flatMap((section) =>
    section.fields.filter((field) => field.sweepable),
  )
  const statusText =
    health.data?.status === 'ok' ? 'API ok' : health.isError ? 'API error' : 'Conectando'
  const channelState = states[1].data?.state ?? {}
  const sourceState = states[0].data?.state ?? {}
  const detectorState = states[2].data?.state ?? {}
  const timingState = states[3].data?.state ?? {}
  const digest = validation.data?.digest.slice(0, 8)

  return (
    <main className="min-h-screen bg-background text-slate-100">
      <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[220px_1fr]">
        <aside className="border-b border-border bg-surface px-4 py-4 lg:border-b-0 lg:border-r lg:px-5 lg:py-6">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded bg-cyan/10 text-cyan">
              <RadioTower size={22} aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-semibold text-white">QKD Panel</p>
              <p className="font-mono text-xs text-slate-400">laboratorio local</p>
            </div>
          </div>
          <nav className="grid gap-1 text-sm text-slate-300 sm:grid-cols-4 lg:block lg:space-y-1">
            {[
              ['Biblioteca', Library],
              ['Diseñador', FlaskConical],
              ['Caracterización', Activity],
              ['Curvas', Gauge],
            ].map(([label, Icon]) => (
              <div
                className="flex items-center gap-3 rounded px-3 py-2 hover:bg-white/5"
                key={label as string}
              >
                <Icon size={16} aria-hidden="true" />
                <span>{label as string}</span>
              </div>
            ))}
          </nav>
        </aside>
        <section className="min-w-0 px-4 py-4 sm:px-6 sm:py-5">
          <header className="mb-6 flex flex-col gap-4 border-b border-border pb-5 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-white">
                Diseñador
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                BB84 decoy, fibra y dinámica temporal
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <StatusPill label={statusText} detail={health.data?.service ?? '/api/health'} />
              <StatusPill
                label={
                  validation.isError
                    ? 'Validación error'
                    : validation.isFetching
                      ? 'Validando'
                      : 'Validado'
                }
                detail={
                  validationIssues[0]?.loc ?? (digest ? `Digest ${digest}` : 'Digest pendiente')
                }
                tone={validation.isError ? 'danger' : 'success'}
              />
            </div>
          </header>
          {validationIssues.length > 0 ? <ValidationSummary issues={validationIssues} /> : null}
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-5">
              <SchemaForm
                errors={validationIssues}
                sections={catalogSections}
                scenario={scenario}
                onChange={updateField}
              />
              <DynamicsPanel
                onChange={updateField}
                rows={dynamics.data?.rows ?? []}
                scenario={scenario}
                sweepableFields={sweepableFields}
              />
            </div>
            <aside className="space-y-4">
              <LiveBudget
                channelState={channelState}
                sourceState={sourceState}
                detectorState={detectorState}
                timingState={timingState}
              />
              <MetricList metrics={catalog.data?.metrics ?? []} />
            </aside>
          </div>
        </section>
      </div>
    </main>
  )
}

function StatusPill({
  label,
  detail,
  tone = 'cyan',
}: {
  label: string
  detail: string
  tone?: 'cyan' | 'success' | 'danger'
}) {
  const toneClass =
    tone === 'success' ? 'text-success' : tone === 'danger' ? 'text-danger' : 'text-cyan'
  return (
    <div className="rounded border border-border bg-surface px-4 py-3 text-right">
      <p className={`text-sm font-medium ${toneClass}`}>{label}</p>
      <p className="font-mono text-xs text-slate-400">{detail}</p>
    </div>
  )
}

function ValidationSummary({ issues }: { issues: ApiValidationIssue[] }) {
  return (
    <section className="mb-5 rounded border border-danger/50 bg-danger/10 px-4 py-3">
      <p className="text-sm font-medium text-danger">Validación pendiente</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {issues.slice(0, 4).map((issue) => (
          <span
            className="rounded border border-danger/40 bg-background px-2 py-1 font-mono text-xs text-slate-200"
            key={`${issue.loc}-${issue.msg}`}
          >
            {issue.loc}: {issue.msg}
          </span>
        ))}
      </div>
    </section>
  )
}

function SchemaForm({
  errors,
  sections,
  scenario,
  onChange,
}: {
  errors: ApiValidationIssue[]
  sections: CatalogSection[]
  scenario: Record<string, unknown>
  onChange: (target: string, value: unknown) => void
}) {
  return (
    <div className="space-y-4">
      {sections
        .filter((section) => section.key !== 'dynamic')
        .map((section) => {
          const visibleFields = section.fields.filter((field) => isFieldVisible(field, scenario))
          if (visibleFields.length === 0) {
            return null
          }
          return (
            <section className="rounded border border-border bg-surface" key={section.key}>
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold text-white">{section.label_es}</h2>
                <span className="text-xs text-slate-500">{visibleFields.length}</span>
              </div>
              <div className="grid grid-cols-1 gap-3 p-4 md:grid-cols-2">
                {visibleFields.map((field) => (
                  <SchemaField
                    error={fieldError(errors, field.key)}
                    field={field}
                    key={field.key}
                    onChange={onChange}
                    value={readTarget(scenario, field.key) ?? field.default}
                  />
                ))}
              </div>
            </section>
          )
        })}
    </div>
  )
}

function SchemaField({
  error,
  field,
  value,
  onChange,
}: {
  error: string | null
  field: CatalogField
  value: unknown
  onChange: (target: string, value: unknown) => void
}) {
  const wide = ['json', 'table', 'schedule_list'].includes(field.type)
  return (
    <div
      className={`block rounded border bg-background/60 p-3 ${
        error ? 'border-danger/70' : 'border-border/80'
      } ${wide ? 'md:col-span-2' : ''}`}
    >
      <span className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <span className="text-sm text-slate-200">{field.label_es}</span>
        <code className="break-all font-mono text-[11px] text-slate-500">{field.key}</code>
      </span>
      <div className="mt-2 flex min-w-0 items-start gap-2">
        <FieldControl field={field} onChange={onChange} value={value} />
        {field.unit ? <span className="w-12 text-xs text-slate-500">{field.unit}</span> : null}
        {field.sweepable ? <CheckCircle2 aria-hidden="true" className="text-cyan" size={15} /> : null}
      </div>
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
    </div>
  )
}

function FieldControl({
  field,
  value,
  onChange,
}: {
  field: CatalogField
  value: unknown
  onChange: (target: string, value: unknown) => void
}) {
  if (field.type === 'boolean') {
    return (
      <input
        checked={Boolean(value)}
        className="mt-2 h-4 w-4 accent-cyan"
        onChange={(event) => onChange(field.key, event.target.checked)}
        type="checkbox"
      />
    )
  }
  if (field.type === 'select' && field.options?.length) {
    return (
      <select
        className="h-9 min-w-0 flex-1 rounded border border-border bg-surface px-3 text-sm text-white outline-none focus:border-cyan"
        onChange={(event) => onChange(field.key, event.target.value)}
        value={formatInputValue(value)}
      >
        {field.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    )
  }
  if (field.type === 'table') {
    return <DecoyTable onChange={(next) => onChange(field.key, next)} value={value} />
  }
  if (field.type === 'number_list' || field.type === 'string_list') {
    return (
      <ListInput
        numeric={field.type === 'number_list'}
        onChange={(next) => onChange(field.key, next)}
        value={value}
      />
    )
  }
  if (field.type === 'json' || field.type === 'schedule_list') {
    return <JsonEditor onChange={(next) => onChange(field.key, next)} value={value} />
  }
  return (
    <NumberOrTextInput
      field={field}
      onChange={(next) => onChange(field.key, next)}
      value={value}
    />
  )
}

function NumberOrTextInput({
  field,
  value,
  onChange,
}: {
  field: CatalogField
  value: unknown
  onChange: (value: unknown) => void
}) {
  const isNumber = field.type === 'number' || field.type === 'integer'
  const numericValue = typeof value === 'number' ? value : Number(value)
  const canSlide =
    isNumber &&
    typeof field.min === 'number' &&
    typeof field.max === 'number' &&
    field.max > field.min &&
    (field.scale !== 'log' || field.min > 0)
  return (
    <div className="min-w-0 flex-1 space-y-2">
      <input
        className="h-9 w-full rounded border border-border bg-surface px-3 font-mono text-sm text-white outline-none focus:border-cyan"
        max={field.max ?? undefined}
        min={field.min ?? undefined}
        onChange={(event) => onChange(parseInputValue(event.target.value, field.type))}
        step={field.step ?? (field.type === 'integer' ? 1 : 'any')}
        type={isNumber ? 'number' : 'text'}
        value={formatInputValue(value)}
      />
      {canSlide ? (
        <input
          className="h-2 w-full accent-cyan"
          max={sliderMax(field)}
          min={sliderMin(field)}
          onChange={(event) => onChange(valueFromSlider(Number(event.target.value), field))}
          step={field.scale === 'log' ? 0.01 : (field.step ?? 0.01)}
          type="range"
          value={valueToSlider(numericValue, field)}
        />
      ) : null}
    </div>
  )
}

function ListInput({
  numeric,
  value,
  onChange,
}: {
  numeric: boolean
  value: unknown
  onChange: (value: unknown[]) => void
}) {
  const items = Array.isArray(value) ? value : []
  return (
    <input
      className="h-9 min-w-0 flex-1 rounded border border-border bg-surface px-3 font-mono text-sm text-white outline-none focus:border-cyan"
      onChange={(event) => {
        const parts = event.target.value
          .split(',')
          .map((part) => part.trim())
          .filter(Boolean)
        onChange(numeric ? parts.map(Number) : parts)
      }}
      value={items.join(', ')}
    />
  )
}

function JsonEditor({
  value,
  onChange,
}: {
  value: unknown
  onChange: (value: unknown) => void
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2))
  const [error, setError] = useState<string | null>(null)

  return (
    <div className="min-w-0 flex-1">
      <textarea
        className="min-h-28 w-full rounded border border-border bg-surface px-3 py-2 font-mono text-xs text-white outline-none focus:border-cyan"
        onBlur={() => {
          try {
            onChange(JSON.parse(text))
            setError(null)
          } catch {
            setError('JSON inválido')
          }
        }}
        onChange={(event) => setText(event.target.value)}
        value={text}
      />
      {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
    </div>
  )
}

function DecoyTable({
  value,
  onChange,
}: {
  value: unknown
  onChange: (value: Array<Record<string, unknown>>) => void
}) {
  const rows = Array.isArray(value) ? value.filter(isRecord) : []
  const probabilitySum = rows.reduce(
    (total, row) => total + Number(row.selection_probability ?? 0),
    0,
  )
  const updateRow = (index: number, key: string, nextValue: unknown) => {
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: nextValue } : row)))
  }
  return (
    <div className="min-w-0 flex-1 space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="pb-2 font-medium">nombre</th>
              <th className="pb-2 font-medium">μ</th>
              <th className="pb-2 font-medium">p</th>
              <th className="w-10 pb-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.map((row, index) => (
              <tr key={`${row.name}-${index}`}>
                <td className="py-2 pr-2">
                  <input
                    className="h-8 w-full rounded border border-border bg-surface px-2 text-white outline-none focus:border-cyan"
                    onChange={(event) => updateRow(index, 'name', event.target.value)}
                    value={formatInputValue(row.name)}
                  />
                </td>
                <td className="py-2 pr-2">
                  <input
                    className="h-8 w-full rounded border border-border bg-surface px-2 font-mono text-white outline-none focus:border-cyan"
                    min={0}
                    onChange={(event) =>
                      updateRow(index, 'mean_photon_number', Number(event.target.value))
                    }
                    step="any"
                    type="number"
                    value={formatInputValue(row.mean_photon_number)}
                  />
                </td>
                <td className="py-2 pr-2">
                  <input
                    className="h-8 w-full rounded border border-border bg-surface px-2 font-mono text-white outline-none focus:border-cyan"
                    max={1}
                    min={0}
                    onChange={(event) =>
                      updateRow(index, 'selection_probability', Number(event.target.value))
                    }
                    step={0.01}
                    type="number"
                    value={formatInputValue(row.selection_probability)}
                  />
                </td>
                <td className="py-2">
                  <button
                    aria-label="Eliminar intensidad decoy"
                    className="flex h-8 w-8 items-center justify-center rounded border border-border text-slate-400 hover:border-danger hover:text-danger"
                    onClick={() => onChange(rows.filter((_, rowIndex) => rowIndex !== index))}
                    title="Eliminar"
                    type="button"
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span
          className={`font-mono text-xs ${
            Math.abs(probabilitySum - 1) < 1e-9 ? 'text-success' : 'text-warning'
          }`}
        >
          Suma p = {probabilitySum.toFixed(3)}
        </span>
        <button
          className="flex h-8 w-8 items-center justify-center rounded border border-border text-cyan hover:bg-cyan/10"
          onClick={() =>
            onChange([
              ...rows,
              { name: `decoy_${rows.length + 1}`, mean_photon_number: 0, selection_probability: 0 },
            ])
          }
          title="Añadir"
          type="button"
        >
          <Plus size={15} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

function LiveBudget({
  channelState,
  sourceState,
  detectorState,
  timingState,
}: {
  channelState: Record<string, unknown>
  sourceState: Record<string, unknown>
  detectorState: Record<string, unknown>
  timingState: Record<string, unknown>
}) {
  return (
    <section className="rounded border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-white">Link budget</h2>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <MetricCard label="loss_dB" value={formatNumber(channelState.loss_db, ' dB')} />
        <MetricCard label="eta" value={formatNumber(channelState.transmittance)} />
        <MetricCard label="p_dark" value={formatNumber(detectorState.p_dark_per_gate)} />
        <MetricCard label="sigma" value={formatNumber(timingState.effective_jitter_std_s, ' s')} />
        <MetricCard label="fotones/s" value={formatNumber(sourceState.mean_photon_rate_hz)} />
      </div>
    </section>
  )
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <article className="rounded border border-border bg-background/60 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-2 font-mono text-lg text-white">{value}</p>
    </article>
  )
}

function DynamicsPanel({
  rows,
  scenario,
  sweepableFields,
  onChange,
}: {
  rows: Array<Record<string, unknown>>
  scenario: Record<string, unknown>
  sweepableFields: CatalogField[]
  onChange: (target: string, value: unknown) => void
}) {
  const schedule = firstSchedule(scenario, sweepableFields)
  const scheduleTarget = String(schedule.target ?? sweepableFields[0]?.key ?? 'channel.distance_km')
  const normalizedSchedule = { ...schedule, target: scheduleTarget }
  const profile = isRecord(schedule.profile)
    ? schedule.profile
    : defaultProfile(scheduleTarget, scenario)
  const x = rows.map((row) => Number(row.time_s ?? 0))
  const y = rows.map((row) =>
    Number(row[scheduleTarget] ?? readTarget(scenario, scheduleTarget) ?? 0),
  )
  const profileKind = String(profile.kind ?? 'constant')
  const updateSchedule = (next: Record<string, unknown>) =>
    onChange('dynamic.parameter_schedules', [next])
  const updateProfile = (key: string, value: unknown) =>
    updateSchedule({ ...normalizedSchedule, profile: { ...profile, [key]: value } })
  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-sm font-semibold text-white">Dinámica</h2>
        <span className="break-all font-mono text-xs text-slate-500">{scheduleTarget}</span>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-4">
        <label className="block">
          <span className="text-xs text-slate-500">target</span>
          <select
            className="mt-1 h-9 w-full rounded border border-border bg-background px-2 font-mono text-xs text-white outline-none focus:border-cyan"
            onChange={(event) =>
              updateSchedule({
                target: event.target.value,
                profile: defaultProfile(event.target.value, scenario),
              })
            }
            value={scheduleTarget}
          >
            {sweepableFields.map((field) => (
              <option key={field.key} value={field.key}>
                {field.key}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-xs text-slate-500">perfil</span>
          <select
            className="mt-1 h-9 w-full rounded border border-border bg-background px-2 text-xs text-white outline-none focus:border-cyan"
            onChange={(event) =>
              updateSchedule({
                ...normalizedSchedule,
                profile: profileForKind(event.target.value, profile),
              })
            }
            value={profileKind}
          >
            <option value="constant">constant</option>
            <option value="linear">linear</option>
            <option value="exponential">exponential</option>
          </select>
        </label>
        <MiniNumberInput
          label="start_s"
          onChange={(value) => updateProfile('start_s', value)}
          value={Number(profile.start_s ?? 0)}
        />
        <MiniNumberInput
          label="end_s"
          onChange={(value) => updateProfile('end_s', value)}
          value={Number(profile.end_s ?? 0.001)}
        />
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
        {profileKind === 'constant' ? (
          <MiniNumberInput
            label="value"
            onChange={(value) => updateProfile('value', value)}
            value={Number(profile.value ?? 0)}
          />
        ) : (
          <>
            <MiniNumberInput
              label="start_value"
              onChange={(value) => updateProfile('start_value', value)}
              value={Number(profile.start_value ?? 0)}
            />
            <MiniNumberInput
              label="end_value"
              onChange={(value) => updateProfile('end_value', value)}
              value={Number(profile.end_value ?? 0)}
            />
            {profileKind === 'exponential' ? (
              <MiniNumberInput
                label="curve"
                onChange={(value) => updateProfile('curve', value)}
                value={Number(profile.curve ?? 4)}
              />
            ) : null}
          </>
        )}
      </div>
      <div className="mt-3 h-56">
        <Plot
          config={{ displayModeBar: false, responsive: true }}
          data={[
            {
              x,
              y,
              mode: 'lines+markers',
              type: 'scatter',
              marker: { color: '#22d3ee' },
              line: { color: '#22d3ee' },
            },
          ]}
          layout={{
            ...qkdPlotlyLayout,
            autosize: true,
            height: 220,
            xaxis: { ...qkdPlotlyLayout.xaxis, title: { text: 't (s)' } },
            yaxis: { ...qkdPlotlyLayout.yaxis, title: { text: scheduleTarget } },
          }}
          style={{ height: '100%', width: '100%' }}
        />
      </div>
    </section>
  )
}

function MiniNumberInput({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (value: number) => void
}) {
  return (
    <label className="block">
      <span className="text-xs text-slate-500">{label}</span>
      <input
        className="mt-1 h-9 w-full rounded border border-border bg-background px-2 font-mono text-xs text-white outline-none focus:border-cyan"
        onChange={(event) => onChange(Number(event.target.value))}
        step="any"
        type="number"
        value={Number.isFinite(value) ? value : 0}
      />
    </label>
  )
}

function MetricList({
  metrics,
}: {
  metrics: Array<{ key: string; label_es: string; unit: string | null }>
}) {
  return (
    <section className="rounded border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-white">Métricas</h2>
      <div className="mt-3 flex flex-wrap gap-2">
        {metrics.slice(0, 16).map((metric) => (
          <span
            className="rounded border border-border bg-background px-2 py-1 font-mono text-xs text-slate-300"
            key={metric.key}
          >
            {metric.key}
          </span>
        ))}
      </div>
    </section>
  )
}

function readTarget(scenario: Record<string, unknown>, target: string): unknown {
  const [section, field] = target.split('.')
  if (section === 'scenario') {
    return scenario[field]
  }
  const sectionValue = scenario[section]
  if (!isRecord(sectionValue)) {
    return undefined
  }
  return sectionValue[field]
}

function parseInputValue(value: string, type: string): unknown {
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

function formatInputValue(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }
  return String(value)
}

function formatNumber(value: unknown, suffix = ''): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '...'
  }
  return `${value.toFixed(value === 0 ? 0 : value < 0.01 ? 6 : 2)}${suffix}`
}

function isFieldVisible(field: CatalogField, scenario: Record<string, unknown>): boolean {
  if (!field.visible_when) {
    return true
  }
  return readTarget(scenario, field.visible_when.target) === field.visible_when.equals
}

function fieldError(errors: ApiValidationIssue[], fieldKey: string): string | null {
  return errors.find((error) => error.loc === fieldKey)?.msg ?? null
}

function sliderMin(field: CatalogField): number {
  const minimum = field.min ?? 0
  return field.scale === 'log' ? Math.log10(minimum) : minimum
}

function sliderMax(field: CatalogField): number {
  const maximum = field.max ?? 1
  return field.scale === 'log' ? Math.log10(maximum) : maximum
}

function valueToSlider(value: number, field: CatalogField): number {
  const minimum = field.min ?? 0
  if (field.scale === 'log') {
    return Math.log10(Math.max(value, minimum))
  }
  return Number.isFinite(value) ? value : minimum
}

function valueFromSlider(value: number, field: CatalogField): number {
  const rawValue = field.scale === 'log' ? 10 ** value : value
  return field.type === 'integer' ? Math.round(rawValue) : rawValue
}

function firstSchedule(
  scenario: Record<string, unknown>,
  sweepableFields: CatalogField[],
): Record<string, unknown> {
  const schedules = readTarget(scenario, 'dynamic.parameter_schedules')
  if (Array.isArray(schedules) && isRecord(schedules[0])) {
    return schedules[0]
  }
  const target = sweepableFields[0]?.key ?? 'channel.distance_km'
  return { target, profile: defaultProfile(target, scenario) }
}

function defaultProfile(
  target: string,
  scenario: Record<string, unknown>,
): Record<string, unknown> {
  const currentValue = readTarget(scenario, target)
  return {
    kind: 'constant',
    start_s: 0,
    end_s: 0.001,
    value: typeof currentValue === 'number' ? currentValue : 0,
  }
}

function profileForKind(kind: string, current: Record<string, unknown>): Record<string, unknown> {
  const start_s = Number(current.start_s ?? 0)
  const end_s = Number(current.end_s ?? 0.001)
  if (kind === 'constant') {
    return { kind, start_s, end_s, value: Number(current.value ?? current.end_value ?? 0) }
  }
  const profile = {
    kind,
    start_s,
    end_s,
    start_value: Number(current.start_value ?? current.value ?? 0),
    end_value: Number(current.end_value ?? current.value ?? 0),
  }
  return kind === 'exponential' ? { ...profile, curve: Number(current.curve ?? 4) } : profile
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value)

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedValue(value), delayMs)
    return () => window.clearTimeout(timeout)
  }, [delayMs, value])

  return debouncedValue
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PanelShell />
    </QueryClientProvider>
  )
}

export default App
