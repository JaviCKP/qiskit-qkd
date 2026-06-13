import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQueries,
  useQuery,
} from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { ChangeEvent, ComponentType } from 'react'
import type { PlotParams } from 'react-plotly.js'
import {
  Activity,
  CheckCircle2,
  Copy,
  Download,
  FlaskConical,
  Gauge,
  Library,
  Plus,
  Play,
  RadioTower,
  Save,
  Square,
  Trash2,
  Upload,
} from 'lucide-react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponentModule from 'react-plotly.js/factory'

import {
  ApiError,
  cancelSweep,
  cancelRun,
  characterize,
  createExperiment,
  createRun,
  createSweep,
  deleteExperiment,
  exportExperiment,
  fetchRunResult,
  fetchRunStatus,
  fetchSweepStatus,
  fetchCatalog,
  importExperiment,
  type AxisRequest,
  type ApiValidationIssue,
  type CatalogField,
  type CatalogSection,
  type Experiment,
  type JobStatus,
  listExperiments,
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

type ActiveView = 'library' | 'designer' | 'characterize' | 'results' | 'curves'

type RunSnapshot = {
  digest: string
  status: JobStatus
  result: Record<string, unknown>
}

function PanelShell() {
  const scenario = useDesignerStore((state) => state.scenario)
  const loadScenario = useDesignerStore((state) => state.loadScenario)
  const updateField = useDesignerStore((state) => state.updateField)
  const [activeView, setActiveView] = useState<ActiveView>('designer')
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
  const navItems = [
    { id: 'library' as const, label: 'Biblioteca', Icon: Library },
    { id: 'designer' as const, label: 'Diseñador', Icon: FlaskConical },
    { id: 'characterize' as const, label: 'Caracterización', Icon: Activity },
    { id: 'results' as const, label: 'Ejecución', Icon: Activity },
    { id: 'curves' as const, label: 'Curvas', Icon: Gauge },
  ]
  const title =
    activeView === 'library'
      ? 'Biblioteca'
      : activeView === 'characterize'
        ? 'Caracterización'
      : activeView === 'results'
        ? 'Ejecución y resultados'
        : activeView === 'curves'
          ? 'Curvas'
          : 'Diseñador'
  const subtitle =
    activeView === 'library'
      ? 'experimentos persistentes JSON'
      : activeView === 'characterize'
        ? 'estado analítico del enlace'
      : activeView === 'results'
        ? 'jobs, métricas, eventos y guardado'
        : activeView === 'curves'
          ? 'recetas de barrido pendientes'
          : 'BB84 decoy, fibra y dinámica temporal'

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
          <nav className="grid gap-1 text-sm text-slate-300 sm:grid-cols-5 lg:block lg:space-y-1">
            {navItems.map(({ id, label, Icon }) => (
              <button
                className={`flex items-center gap-3 rounded px-3 py-2 text-left hover:bg-white/5 ${
                  activeView === id ? 'bg-white/5 text-cyan' : ''
                }`}
                key={id}
                onClick={() => setActiveView(id)}
                type="button"
              >
                <Icon size={16} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </nav>
        </aside>
        <section className="min-w-0 px-4 py-4 sm:px-6 sm:py-5">
          <header className="mb-6 flex flex-col gap-4 border-b border-border pb-5 md:flex-row md:items-center md:justify-between">
            <div>
              <h1 className="text-2xl font-semibold tracking-normal text-white">{title}</h1>
              <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
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
          {activeView === 'designer' ? (
            <>
              {validationIssues.length > 0 ? (
                <ValidationSummary issues={validationIssues} />
              ) : null}
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
            </>
          ) : activeView === 'library' ? (
            <LibraryView
              currentScenario={scenario}
              onLoad={(nextScenario) => {
                loadScenario(nextScenario)
                setActiveView('designer')
              }}
            />
          ) : activeView === 'characterize' ? (
            <CharacterizationView
              scenario={scenario}
              sweepableFields={sweepableFields}
            />
          ) : activeView === 'results' ? (
            <ExecutionView scenario={scenario} />
          ) : (
            <CurvesView
              metrics={catalog.data?.metrics ?? []}
              scenario={scenario}
              sweepableFields={sweepableFields}
            />
          )}
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

function ExecutionView({ scenario }: { scenario: Record<string, unknown> }) {
  const [label, setLabel] = useState('run local')
  const [saveName, setSaveName] = useState('Experimento dashboard')
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [runs, setRuns] = useState<RunSnapshot[]>([])
  const latestRun = runs.at(-1) ?? null
  const previousRun = runs.length > 1 ? runs.at(-2) ?? null : null
  const pulses = Number(readTarget(scenario, 'scenario.pulses') ?? 0)
  const runMutation = useMutation({
    mutationFn: async (): Promise<RunSnapshot> => {
      const created = await createRun(scenario, label)
      setActiveJobId(created.job_id)
      let status = await fetchRunStatus(created.job_id)
      setJobStatus(status)
      while (status.status === 'queued' || status.status === 'running') {
        await delay(500)
        status = await fetchRunStatus(created.job_id)
        setJobStatus(status)
      }
      if (status.status !== 'done') {
        throw new Error(status.error ?? `job ${status.status}`)
      }
      const result = await fetchRunResult(created.job_id)
      return { digest: created.digest, status, result }
    },
    onSuccess: (snapshot) => {
      setRuns((current) => [...current, snapshot])
      setSaveName(label || `Experimento ${snapshot.digest.slice(0, 8)}`)
      setActiveJobId(null)
    },
    onError: () => setActiveJobId(null),
  })
  const cancelMutation = useMutation({
    mutationFn: async () => (activeJobId ? cancelRun(activeJobId) : { cancelled: false }),
    onSuccess: () => {
      setJobStatus((current) => (current ? { ...current, status: 'cancelled' } : current))
      setActiveJobId(null)
    },
  })
  const saveMutation = useMutation({
    mutationFn: async () =>
      createExperiment({
        name: saveName,
        scenario,
        tags: ['dashboard'],
        last_result: latestRun?.result ?? null,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })
  const progress = jobStatus?.progress
  const progressPercent = progress && progress.total > 0 ? (100 * progress.done) / progress.total : 0

  return (
    <div className="space-y-5">
      <section className="rounded border border-border bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_auto]">
          <label className="block">
            <span className="text-xs text-slate-500">label</span>
            <input
              className="mt-1 h-9 w-full rounded border border-border bg-background px-3 text-sm text-white outline-none focus:border-cyan"
              onChange={(event) => setLabel(event.target.value)}
              value={label}
            />
          </label>
          <button
            className="mt-5 flex h-9 items-center justify-center gap-2 rounded border border-cyan px-3 text-sm text-cyan hover:bg-cyan/10 disabled:opacity-50"
            disabled={runMutation.isPending}
            onClick={() => runMutation.mutate()}
            type="button"
          >
            <Play size={15} aria-hidden="true" />
            Ejecutar
          </button>
          <button
            className="mt-5 flex h-9 items-center justify-center gap-2 rounded border border-border px-3 text-sm text-slate-300 hover:border-warning hover:text-warning disabled:opacity-50"
            disabled={!activeJobId || cancelMutation.isPending}
            onClick={() => cancelMutation.mutate()}
            type="button"
          >
            <Square size={15} aria-hidden="true" />
            Cancelar
          </button>
        </div>
        {jobStatus ? (
          <div className="mt-4">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="font-mono text-slate-300">{jobStatus.job_id}</span>
              <span className="text-slate-500">
                {jobStatus.status} · {jobStatus.elapsed_s.toFixed(2)} s
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-background">
              <div className="h-full bg-cyan" style={{ width: `${progressPercent}%` }} />
            </div>
          </div>
        ) : null}
        {runMutation.error ? (
          <p className="mt-3 text-sm text-danger">{runMutation.error.message}</p>
        ) : null}
        {pulses > 100_000 ? (
          <p className="mt-3 text-sm text-warning">
            Aviso de coste: este escenario supera 1e5 pulsos y puede tardar minutos.
          </p>
        ) : null}
      </section>
      {latestRun ? (
        <>
          <section className="rounded border border-border bg-surface p-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
              <label className="block flex-1">
                <span className="text-xs text-slate-500">guardar como</span>
                <input
                  className="mt-1 h-9 w-full rounded border border-border bg-background px-3 text-sm text-white outline-none focus:border-cyan"
                  onChange={(event) => setSaveName(event.target.value)}
                  value={saveName}
                />
              </label>
              <button
                className="flex h-9 items-center justify-center gap-2 rounded border border-success px-3 text-sm text-success hover:bg-success/10 disabled:opacity-50"
                disabled={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
                type="button"
              >
                <Save size={15} aria-hidden="true" />
                Guardar
              </button>
            </div>
            {saveMutation.data ? (
              <p className="mt-2 font-mono text-xs text-success">
                guardado {saveMutation.data.experiment.id}
              </p>
            ) : null}
          </section>
          <ResultDetails latestRun={latestRun} previousRun={previousRun} />
        </>
      ) : (
        <section className="rounded border border-border bg-surface p-4 text-sm text-slate-400">
          Ejecuta el escenario actual para ver métricas, eventos y provenance.
        </section>
      )}
    </div>
  )
}

function ResultDetails({
  latestRun,
  previousRun,
}: {
  latestRun: RunSnapshot
  previousRun: RunSnapshot | null
}) {
  const [activeTab, setActiveTab] = useState('summary')
  const summary = latestRun.status.result_summary ?? {}
  const previousSummary = previousRun?.status.result_summary ?? null
  const tabs = resultTabs(latestRun.result, summary)
  const selectedTab = tabs.includes(activeTab) ? activeTab : tabs[0]

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Resultado</h2>
          <p className="font-mono text-xs text-slate-500">{latestRun.digest.slice(0, 12)}</p>
        </div>
        <StatusBadge summary={summary} />
      </div>
      <ResultMetricGrid current={summary} previous={previousSummary} />
      <div className="mt-5 flex flex-wrap gap-2 border-b border-border pb-3">
        {tabs.map((tab) => (
          <button
            className={`rounded px-3 py-1 text-sm ${
              selectedTab === tab ? 'bg-cyan/10 text-cyan' : 'text-slate-400 hover:text-white'
            }`}
            key={tab}
            onClick={() => setActiveTab(tab)}
            type="button"
          >
            {tabLabel(tab)}
          </button>
        ))}
      </div>
      <div className="mt-4">{renderResultTab(selectedTab, latestRun.result, summary)}</div>
    </section>
  )
}

function LibraryView({
  currentScenario,
  onLoad,
}: {
  currentScenario: Record<string, unknown>
  onLoad: (scenario: Record<string, unknown>) => void
}) {
  const [name, setName] = useState('Experimento dashboard')
  const experiments = useQuery({ queryKey: ['experiments'], queryFn: listExperiments })
  const saveCurrent = useMutation({
    mutationFn: async () =>
      createExperiment({ name, scenario: currentScenario, tags: ['dashboard'] }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })
  const duplicate = useMutation({
    mutationFn: async (experiment: Experiment) =>
      createExperiment({
        name: `${experiment.name} copia`,
        scenario: experiment.scenario,
        tags: experiment.tags ?? [],
        last_result: experiment.last_result ?? null,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })
  const remove = useMutation({
    mutationFn: deleteExperiment,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })
  const importer = useMutation({
    mutationFn: importExperiment,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })

  return (
    <div className="space-y-5">
      <section className="rounded border border-border bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto]">
          <label className="block">
            <span className="text-xs text-slate-500">nombre</span>
            <input
              className="mt-1 h-9 w-full rounded border border-border bg-background px-3 text-sm text-white outline-none focus:border-cyan"
              onChange={(event) => setName(event.target.value)}
              value={name}
            />
          </label>
          <button
            className="mt-5 flex h-9 items-center justify-center gap-2 rounded border border-success px-3 text-sm text-success hover:bg-success/10"
            onClick={() => saveCurrent.mutate()}
            type="button"
          >
            <Save size={15} aria-hidden="true" />
            Guardar actual
          </button>
          <label className="mt-5 flex h-9 cursor-pointer items-center justify-center gap-2 rounded border border-border px-3 text-sm text-slate-300 hover:border-cyan hover:text-cyan">
            <Upload size={15} aria-hidden="true" />
            Importar
            <input
              className="hidden"
              onChange={(event) => void importFromFile(event, importer.mutate)}
              type="file"
              accept="application/json"
            />
          </label>
        </div>
      </section>
      <section className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {(experiments.data?.experiments ?? []).map((experiment) => (
          <article className="rounded border border-border bg-surface p-4" key={experiment.id}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-white">{experiment.name}</h2>
                <p className="mt-1 font-mono text-xs text-slate-500">
                  {experiment.digest.slice(0, 12)}
                </p>
                {experiment.curve_recipes?.length ? (
                  <p className="mt-1 text-xs text-cyan">
                    {experiment.curve_recipes.length} receta(s) de curva
                  </p>
                ) : null}
              </div>
              <StatusBadge summary={experiment.last_result ?? {}} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                className="flex h-8 items-center gap-2 rounded border border-cyan px-2 text-xs text-cyan hover:bg-cyan/10"
                onClick={() => onLoad(experiment.scenario)}
                type="button"
              >
                <FlaskConical size={14} aria-hidden="true" />
                Cargar
              </button>
              <button
                className="flex h-8 items-center gap-2 rounded border border-border px-2 text-xs text-slate-300 hover:text-white"
                onClick={() => duplicate.mutate(experiment)}
                type="button"
              >
                <Copy size={14} aria-hidden="true" />
                Duplicar
              </button>
              <button
                className="flex h-8 items-center gap-2 rounded border border-border px-2 text-xs text-slate-300 hover:text-white"
                onClick={() => void exportToFile(experiment)}
                type="button"
              >
                <Download size={14} aria-hidden="true" />
                Exportar
              </button>
              <button
                className="flex h-8 items-center gap-2 rounded border border-border px-2 text-xs text-slate-300 hover:border-danger hover:text-danger"
                onClick={() => remove.mutate(experiment.id)}
                type="button"
              >
                <Trash2 size={14} aria-hidden="true" />
                Borrar
              </button>
            </div>
          </article>
        ))}
      </section>
    </div>
  )
}

function CharacterizationView({
  scenario,
  sweepableFields,
}: {
  scenario: Record<string, unknown>
  sweepableFields: CatalogField[]
}) {
  const [section, setSection] = useState<'source' | 'channel' | 'detector' | 'timing'>('source')
  const [axisTarget, setAxisTarget] = useState('channel.distance_km')
  const [start, setStart] = useState(0)
  const [stop, setStop] = useState(100)
  const state = useQuery({
    queryKey: ['characterize-view', section, scenario],
    queryFn: () => characterize(section, scenario),
  })
  const axis: AxisRequest = {
    target: axisTarget,
    values: { start, stop, steps: 25, scale: 'linear' },
  }
  const curve = useQuery({
    queryKey: ['characterize-curve', section, scenario, axis],
    queryFn: () => characterize(section, scenario, axis),
  })
  const stateRows = Object.entries(state.data?.state ?? {})
  const rows = curve.data?.rows ?? []
  const yKey = firstNumericKey(rows, axisTarget)

  return (
    <div className="space-y-5">
      <section className="rounded border border-border bg-surface p-4">
        <div className="flex flex-wrap gap-2">
          {(['source', 'channel', 'detector', 'timing'] as const).map((item) => (
            <button
              className={`rounded px-3 py-1 text-sm ${
                section === item ? 'bg-cyan/10 text-cyan' : 'text-slate-400 hover:text-white'
              }`}
              key={item}
              onClick={() => setSection(item)}
              type="button"
            >
              {item}
            </button>
          ))}
        </div>
        <p className="mt-4 font-mono text-xs text-slate-500">{formulaForSection(section)}</p>
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {stateRows.slice(0, 12).map(([key, value]) => (
            <MetricCard key={key} label={key} value={formatNumberOrText(value)} />
          ))}
        </div>
      </section>
      <section className="rounded border border-border bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_120px_120px]">
          <label className="block">
            <span className="text-xs text-slate-500">axis</span>
            <select
              className="mt-1 h-9 w-full rounded border border-border bg-background px-2 font-mono text-xs text-white outline-none focus:border-cyan"
              onChange={(event) => setAxisTarget(event.target.value)}
              value={axisTarget}
            >
              {sweepableFields.map((field) => (
                <option key={field.key} value={field.key}>
                  {field.key}
                </option>
              ))}
            </select>
          </label>
          <MiniNumberInput label="start" onChange={setStart} value={start} />
          <MiniNumberInput label="stop" onChange={setStop} value={stop} />
        </div>
        <div className="mt-4 h-72">
          <Plot
            config={{ displayModeBar: true, responsive: true }}
            data={[
              {
                x: rows.map((row) => Number(row[axisTarget] ?? 0)),
                y: rows.map((row) => Number(row[yKey] ?? 0)),
                mode: 'lines+markers',
                type: 'scatter',
                marker: { color: '#22d3ee' },
                line: { color: '#22d3ee' },
              },
            ]}
            layout={{
              ...qkdPlotlyLayout,
              autosize: true,
              height: 280,
              xaxis: { ...qkdPlotlyLayout.xaxis, title: { text: axisTarget } },
              yaxis: { ...qkdPlotlyLayout.yaxis, title: { text: yKey } },
            }}
            style={{ height: '100%', width: '100%' }}
          />
        </div>
      </section>
    </div>
  )
}

function CurvesView({
  metrics,
  scenario,
  sweepableFields,
}: {
  metrics: Array<{ key: string; label_es: string; unit: string | null }>
  scenario: Record<string, unknown>
  sweepableFields: CatalogField[]
}) {
  const [axisTarget, setAxisTarget] = useState('channel.distance_km')
  const [metric, setMetric] = useState('secret_key_rate_bps')
  const [start, setStart] = useState(0)
  const [stop, setStop] = useState(120)
  const [steps, setSteps] = useState(5)
  const [repeats, setRepeats] = useState(1)
  const [scale, setScale] = useState<'linear' | 'log'>('linear')
  const [seriesTarget, setSeriesTarget] = useState('')
  const [seriesValues, setSeriesValues] = useState('0.6, 0.8, 0.95')
  const [sweepStatus, setSweepStatus] = useState<JobStatus | null>(null)
  const [activeSweepId, setActiveSweepId] = useState<string | null>(null)
  const sweep = useMutation({
    mutationFn: async (): Promise<Record<string, unknown>> => {
      const axis: AxisRequest = { target: axisTarget, values: { start, stop, steps, scale } }
      const series = seriesTarget
        ? { target: seriesTarget, values: parseSeriesValues(seriesValues) }
        : null
      const created = await createSweep({ scenario, axis, series, repeats })
      setActiveSweepId(created.job_id)
      let status = await fetchSweepStatus(created.job_id)
      setSweepStatus(status)
      while (status.status === 'queued' || status.status === 'running') {
        await delay(500)
        status = await fetchSweepStatus(created.job_id)
        setSweepStatus(status)
      }
      setActiveSweepId(null)
      if (status.status !== 'done' || !status.result) {
        throw new Error(status.error ?? `sweep ${status.status}`)
      }
      return status.result
    },
    onError: () => setActiveSweepId(null),
  })
  const cancel = useMutation({
    mutationFn: async () => (activeSweepId ? cancelSweep(activeSweepId) : { cancelled: false }),
    onSuccess: () => {
      setSweepStatus((current) => (current ? { ...current, status: 'cancelled' } : current))
      setActiveSweepId(null)
    },
  })
  const saveRecipe = useMutation({
    mutationFn: async () =>
      createExperiment({
        name: `Curva ${metric} vs ${axisTarget}`,
        scenario,
        tags: ['curve'],
        curve_recipes: [
          {
            axis: { target: axisTarget, values: { start, stop, steps, scale } },
            metric,
            repeats,
            series: seriesTarget
              ? { target: seriesTarget, values: parseSeriesValues(seriesValues) }
              : null,
          },
        ],
        last_result: sweep.data ?? null,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiments'] }),
  })
  const rows = Array.isArray(sweep.data?.rows) ? sweep.data.rows.filter(isRecord) : []
  const summaryRows = Array.isArray(sweep.data?.summary)
    ? sweep.data.summary.filter(isRecord)
    : []
  const plotRows = summaryRows.some((row) => `${metric}_mean` in row) ? summaryRows : rows
  const traces = curveTraces(plotRows, axisTarget, metric, seriesTarget)
  const progress = sweepStatus?.progress
  const progressPercent = progress && progress.total > 0 ? (100 * progress.done) / progress.total : 0

  return (
    <div className="space-y-5">
      <section className="rounded border border-border bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_1fr_100px_100px_100px_110px]">
          <SelectField label="eje X" onChange={setAxisTarget} options={['time_s', ...sweepableFields.map((field) => field.key)]} value={axisTarget} />
          <SelectField label="métrica Y" onChange={setMetric} options={metrics.map((item) => item.key)} value={metric} />
          <MiniNumberInput label="start" onChange={setStart} value={start} />
          <MiniNumberInput label="stop" onChange={setStop} value={stop} />
          <MiniNumberInput label="steps" onChange={(value) => setSteps(Math.max(1, Math.round(value)))} value={steps} />
          <MiniNumberInput label="repeats" onChange={(value) => setRepeats(Math.max(1, Math.round(value)))} value={repeats} />
        </div>
        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr]">
          <SelectField
            label="serie"
            onChange={setSeriesTarget}
            options={['', ...sweepableFields.map((field) => field.key)]}
            value={seriesTarget}
          />
          <label className="block">
            <span className="text-xs text-slate-500">valores serie</span>
            <input
              className="mt-1 h-9 w-full rounded border border-border bg-background px-3 font-mono text-xs text-white outline-none focus:border-cyan"
              disabled={!seriesTarget}
              onChange={(event) => setSeriesValues(event.target.value)}
              value={seriesValues}
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button className={scaleButtonClass(scale === 'linear')} onClick={() => setScale('linear')} type="button">lin</button>
          <button className={scaleButtonClass(scale === 'log')} onClick={() => setScale('log')} type="button">log</button>
          <button className="rounded border border-border px-2 py-1 text-xs text-slate-300" onClick={() => applyCurveShortcut('skr', setAxisTarget, setMetric, setStart, setStop, setSteps, setScale)} type="button">SKR vs distancia</button>
          <button className="rounded border border-border px-2 py-1 text-xs text-slate-300" onClick={() => applyCurveShortcut('qber', setAxisTarget, setMetric, setStart, setStop, setSteps, setScale)} type="button">QBER vs distancia</button>
          <button className="rounded border border-border px-2 py-1 text-xs text-slate-300" onClick={() => applyCurveShortcut('eve', setAxisTarget, setMetric, setStart, setStop, setSteps, setScale)} type="button">QBER vs Eve</button>
          <button className="rounded border border-border px-2 py-1 text-xs text-slate-300" onClick={() => applyCurveShortcut('chsh', setAxisTarget, setMetric, setStart, setStop, setSteps, setScale)} type="button">CHSH vs depol</button>
          <button className="rounded border border-border px-2 py-1 text-xs text-slate-300" onClick={() => applyCurveShortcut('decoy', setAxisTarget, setMetric, setStart, setStop, setSteps, setScale)} type="button">gain vs μ</button>
          <button className="rounded border border-border px-2 py-1 text-xs text-slate-300" onClick={() => applyCurveShortcut('time', setAxisTarget, setMetric, setStart, setStop, setSteps, setScale)} type="button">métricas vs tiempo</button>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="flex h-9 items-center gap-2 rounded border border-cyan px-3 text-sm text-cyan hover:bg-cyan/10 disabled:opacity-50" disabled={sweep.isPending} onClick={() => sweep.mutate()} type="button">
            <Play size={15} aria-hidden="true" />
            Ejecutar barrido
          </button>
          <button className="flex h-9 items-center gap-2 rounded border border-border px-3 text-sm text-slate-300 hover:border-warning hover:text-warning disabled:opacity-50" disabled={!activeSweepId} onClick={() => cancel.mutate()} type="button">
            <Square size={15} aria-hidden="true" />
            Cancelar
          </button>
          <button className="flex h-9 items-center gap-2 rounded border border-border px-3 text-sm text-slate-300 hover:text-white disabled:opacity-50" disabled={rows.length === 0} onClick={() => downloadCsv(rows, `${metric}.csv`)} type="button">
            <Download size={15} aria-hidden="true" />
            CSV
          </button>
          <button className="flex h-9 items-center gap-2 rounded border border-border px-3 text-sm text-slate-300 hover:text-white disabled:opacity-50" disabled={rows.length === 0} onClick={() => downloadCurveSvg(rows, axisTarget, metric)} type="button">
            <Download size={15} aria-hidden="true" />
            SVG
          </button>
          <button className="flex h-9 items-center gap-2 rounded border border-success px-3 text-sm text-success hover:bg-success/10 disabled:opacity-50" disabled={saveRecipe.isPending} onClick={() => saveRecipe.mutate()} type="button">
            <Save size={15} aria-hidden="true" />
            Guardar receta
          </button>
        </div>
        {saveRecipe.data ? (
          <p className="mt-2 font-mono text-xs text-success">
            receta guardada {saveRecipe.data.experiment.id}
          </p>
        ) : null}
        {sweepStatus ? (
          <div className="mt-4 h-2 overflow-hidden rounded bg-background">
            <div className="h-full bg-cyan" style={{ width: `${progressPercent}%` }} />
          </div>
        ) : null}
        {sweep.error ? <p className="mt-3 text-sm text-danger">{sweep.error.message}</p> : null}
      </section>
      <section className="rounded border border-border bg-surface p-4">
        <div className="h-96">
          <Plot
            config={{ displayModeBar: true, responsive: true, toImageButtonOptions: { format: 'png' } }}
            data={traces}
            layout={{
              ...qkdPlotlyLayout,
              autosize: true,
              height: 380,
              shapes: metric === 'qber' ? [{ type: 'line', x0: start, x1: stop, y0: 0.11, y1: 0.11, line: { color: '#fbbf24', dash: 'dot' } }] : [],
              xaxis: { ...qkdPlotlyLayout.xaxis, title: { text: axisTarget } },
              yaxis: { ...qkdPlotlyLayout.yaxis, title: { text: metric } },
            }}
            style={{ height: '100%', width: '100%' }}
          />
        </div>
      </section>
    </div>
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

function ResultMetricGrid({
  current,
  previous,
}: {
  current: Record<string, unknown>
  previous: Record<string, unknown> | null
}) {
  const currentMetrics = metricRecord(current)
  const previousMetrics = previous ? metricRecord(previous) : {}
  const keys = ['qber', 'secret_key_rate_bps', 'gain', 'sifted', 'chsh_s']
  return (
    <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {keys.map((key) => (
        <ResultMetricCard
          key={key}
          label={key}
          value={currentMetrics[key]}
          previous={previousMetrics[key]}
        />
      ))}
    </div>
  )
}

function ResultMetricCard({
  label,
  value,
  previous,
}: {
  label: string
  value: unknown
  previous: unknown
}) {
  const delta =
    typeof value === 'number' && typeof previous === 'number' ? value - previous : null
  return (
    <article className="rounded border border-border bg-background/60 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-2 font-mono text-lg text-white">{formatNumber(value)}</p>
      {delta !== null ? (
        <p className={delta >= 0 ? 'text-xs text-success' : 'text-xs text-danger'}>
          Δ {formatNumber(delta)}
        </p>
      ) : (
        <p className="text-xs text-slate-600">sin delta</p>
      )}
    </article>
  )
}

function StatusBadge({ summary }: { summary: Record<string, unknown> }) {
  const metrics = metricRecord(summary)
  const classical = isRecord(summary.classical) ? summary.classical : {}
  const verification = classical.verification_passed
  const abort = metrics.abort === true
  const secure = metrics.secure === true || metrics.abort === false
  const label =
    verification === false ? 'VERIFICACIÓN FALLIDA' : abort ? 'ABORT' : secure ? 'SEGURO' : 'RESULTADO'
  const tone =
    verification === false || abort
      ? 'border-danger text-danger'
      : secure
        ? 'border-success text-success'
        : 'border-border text-slate-300'
  return <span className={`rounded border px-2 py-1 text-xs ${tone}`}>{label}</span>
}

function resultTabs(result: Record<string, unknown>, summary: Record<string, unknown>): string[] {
  const tabs = ['summary']
  if (isRecord(result.decoy) || isRecord(summary.decoy_security)) {
    tabs.push('decoy')
  }
  if (isRecord(result.bell) || isRecord(result.correlations) || isRecord(summary.bell)) {
    tabs.push('bell')
  }
  if (Array.isArray(result.event_sample)) {
    tabs.push('events')
  }
  if (isRecord(result.classical) || isRecord(summary.classical)) {
    tabs.push('classical')
  }
  tabs.push('provenance')
  return tabs
}

function tabLabel(tab: string): string {
  const labels: Record<string, string> = {
    summary: 'Resumen',
    decoy: 'Decoy',
    bell: 'Bell',
    events: 'Eventos',
    classical: 'Clásico',
    provenance: 'Provenance',
  }
  return labels[tab] ?? tab
}

function renderResultTab(
  tab: string,
  result: Record<string, unknown>,
  summary: Record<string, unknown>,
) {
  if (tab === 'events' && Array.isArray(result.event_sample)) {
    return <EventHistogram events={result.event_sample} />
  }
  if (tab === 'decoy') {
    return <JsonBlock value={result.decoy ?? summary.decoy_security ?? {}} />
  }
  if (tab === 'bell') {
    return <JsonBlock value={result.bell ?? result.correlations ?? summary.bell ?? {}} />
  }
  if (tab === 'classical') {
    return <JsonBlock value={result.classical ?? summary.classical ?? {}} />
  }
  if (tab === 'provenance') {
    return <JsonBlock value={result.provenance ?? { digest: summary.digest }} />
  }
  return <JsonBlock value={summary} />
}

function EventHistogram({ events }: { events: unknown[] }) {
  const counts = events.reduce<Record<string, number>>((accumulator, event) => {
    const status = isRecord(event) ? String(event.timing_status ?? 'ok') : 'unknown'
    accumulator[status] = (accumulator[status] ?? 0) + 1
    return accumulator
  }, {})
  const maxCount = Math.max(1, ...Object.values(counts))
  return (
    <div className="space-y-2">
      {Object.entries(counts).map(([status, count]) => (
        <div className="grid grid-cols-[120px_1fr_48px] items-center gap-3" key={status}>
          <span className="font-mono text-xs text-slate-400">{status}</span>
          <div className="h-3 overflow-hidden rounded bg-background">
            <div className="h-full bg-cyan" style={{ width: `${(100 * count) / maxCount}%` }} />
          </div>
          <span className="text-right font-mono text-xs text-slate-400">{count}</span>
        </div>
      ))}
    </div>
  )
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto rounded border border-border bg-background p-3 text-xs text-slate-300">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function SelectField({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="block">
      <span className="text-xs text-slate-500">{label}</span>
      <select
        className="mt-1 h-9 w-full rounded border border-border bg-background px-2 font-mono text-xs text-white outline-none focus:border-cyan"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}

function metricRecord(summary: Record<string, unknown>): Record<string, unknown> {
  return isRecord(summary.metrics) ? summary.metrics : summary
}

function firstNumericKey(rows: Array<Record<string, unknown>>, excluded: string): string {
  for (const row of rows) {
    for (const [key, value] of Object.entries(row)) {
      if (key !== excluded && typeof value === 'number') {
        return key
      }
    }
  }
  return excluded
}

function formulaForSection(section: string): string {
  const formulas: Record<string, string> = {
    source: 'P(0)=e^-μ · P(1)=μe^-μ · P(≥2)=1-e^-μ(1+μ)',
    channel: 'η = 10^(-loss_dB/10)',
    detector: 'p_dark = 1 - exp(-rate · gate)',
    timing: 'p_in_gate = erf(g / (2√2σ))',
  }
  return formulas[section] ?? ''
}

function formatNumberOrText(value: unknown): string {
  return typeof value === 'number' ? formatNumber(value) : formatInputValue(value)
}

function scaleButtonClass(active: boolean): string {
  return `rounded border px-2 py-1 text-xs ${
    active ? 'border-cyan text-cyan' : 'border-border text-slate-300'
  }`
}

function applyCurveShortcut(
  kind: 'skr' | 'qber' | 'eve' | 'chsh' | 'decoy' | 'time',
  setAxisTarget: (value: string) => void,
  setMetric: (value: string) => void,
  setStart: (value: number) => void,
  setStop: (value: number) => void,
  setSteps: (value: number) => void,
  setScale: (value: 'linear' | 'log') => void,
): void {
  if (kind === 'eve') {
    setAxisTarget('eavesdropper.intercept_probability')
    setMetric('qber')
    setStart(0)
    setStop(1)
    setSteps(11)
    setScale('linear')
    return
  }
  if (kind === 'chsh') {
    setAxisTarget('channel.depolarizing_probability')
    setMetric('chsh_s')
    setStart(0)
    setStop(0.2)
    setSteps(11)
    setScale('linear')
    return
  }
  if (kind === 'decoy') {
    setAxisTarget('source.mean_photon_number')
    setMetric('gain')
    setStart(0.01)
    setStop(0.8)
    setSteps(12)
    setScale('linear')
    return
  }
  if (kind === 'time') {
    setAxisTarget('time_s')
    setMetric('qber')
    setStart(0)
    setStop(0.001)
    setSteps(8)
    setScale('linear')
    return
  }
  setAxisTarget('channel.distance_km')
  setMetric(kind === 'skr' ? 'secret_key_rate_bps' : 'qber')
  setStart(0)
  setStop(150)
  setSteps(16)
  setScale('linear')
}

function parseSeriesValues(value: string): Array<number | string | boolean | null> {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      if (part === 'true') {
        return true
      }
      if (part === 'false') {
        return false
      }
      if (part === 'null') {
        return null
      }
      const numeric = Number(part)
      return Number.isFinite(numeric) ? numeric : part
    })
}

function curveTraces(
  rows: Array<Record<string, unknown>>,
  xKey: string,
  metric: string,
  seriesKey: string,
): Array<Record<string, unknown>> {
  const groups = new Map<string, Array<Record<string, unknown>>>()
  for (const row of rows) {
    const group = seriesKey ? String(row[seriesKey] ?? 'serie') : metric
    groups.set(group, [...(groups.get(group) ?? []), row])
  }
  const colors = ['#22d3ee', '#34d399', '#fbbf24', '#8b5cf6', '#f87171', '#e5e7eb']
  return Array.from(groups.entries()).flatMap(([name, groupRows], index) => {
    const color = colors[index % colors.length]
    const meanKey = `${metric}_mean`
    const p05Key = `${metric}_p05`
    const p95Key = `${metric}_p95`
    const yKey = meanKey in (groupRows[0] ?? {}) ? meanKey : metric
    const line = {
      x: groupRows.map((row) => Number(row[xKey] ?? 0)),
      y: groupRows.map((row) => Number(row[yKey] ?? 0)),
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
        x: groupRows.map((row) => Number(row[xKey] ?? 0)),
        y: groupRows.map((row) => Number(row[p95Key] ?? 0)),
        hoverinfo: 'skip',
        line: { color: 'transparent' },
        name: `${name} p95`,
        showlegend: false,
        type: 'scatter',
      },
      {
        x: groupRows.map((row) => Number(row[xKey] ?? 0)),
        y: groupRows.map((row) => Number(row[p05Key] ?? 0)),
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

function downloadCsv(rows: Array<Record<string, unknown>>, fileName: string): void {
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
  const csv = [
    headers.join(','),
    ...rows.map((row) =>
      headers.map((header) => JSON.stringify(row[header] ?? '')).join(','),
    ),
  ].join('\n')
  downloadBlob(fileName, csv, 'text/csv')
}

function downloadCurveSvg(
  rows: Array<Record<string, unknown>>,
  xKey: string,
  yKey: string,
): void {
  const width = 720
  const height = 420
  const points = rows
    .map((row) => [Number(row[xKey] ?? 0), Number(row[yKey] ?? 0)] as const)
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
  const xs = points.map(([x]) => x)
  const ys = points.map(([, y]) => y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const path = points
    .map(([x, y], index) => {
      const px = 60 + ((x - minX) / Math.max(maxX - minX, 1)) * (width - 100)
      const py = height - 50 - ((y - minY) / Math.max(maxY - minY, 1)) * (height - 100)
      return `${index === 0 ? 'M' : 'L'} ${px.toFixed(2)} ${py.toFixed(2)}`
    })
    .join(' ')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="transparent"/><path d="${path}" fill="none" stroke="#22d3ee" stroke-width="3"/><text x="60" y="28" fill="#111827" font-family="monospace">${yKey} vs ${xKey}</text></svg>`
  downloadBlob(`${safeFileName(yKey)}.svg`, svg, 'image/svg+xml')
}

async function exportToFile(experiment: Experiment): Promise<void> {
  const payload = await exportExperiment(experiment.id)
  downloadJson(`${safeFileName(experiment.name)}.json`, payload.experiment)
}

async function importFromFile(
  event: ChangeEvent<HTMLInputElement>,
  onImport: (payload: Record<string, unknown>) => void,
): Promise<void> {
  const file = event.target.files?.[0]
  if (!file) {
    return
  }
  const payload = JSON.parse(await file.text()) as Record<string, unknown>
  onImport(isRecord(payload.experiment) ? payload.experiment : payload)
  event.target.value = ''
}

function downloadJson(fileName: string, value: unknown): void {
  downloadBlob(fileName, JSON.stringify(value, null, 2), 'application/json')
}

function downloadBlob(fileName: string, value: string, type: string): void {
  const blob = new Blob([value], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  URL.revokeObjectURL(url)
}

function safeFileName(value: string): string {
  return value.replace(/[^a-z0-9._-]+/gi, '_').replace(/^_+|_+$/g, '') || 'experiment'
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
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
