import { lazy, Suspense, useCallback, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { FlaskConical, Library, LineChart, RadioTower } from 'lucide-react'

import { ApiError, fetchCatalog, inspectScenario } from '@/api/client'
import { fetchHealthStatus } from '@/api/health'
import { LoadingBlock } from '@/components/ui'
import type { CurveRecipeId } from '@/features/curves/recipes'
import { useDesignerStore } from '@/features/designer/scenarioStore'
import { ExperimentWorkspace } from '@/features/experiment/ExperimentWorkspace'
import { useDebouncedValue } from '@/lib/async'

const CurvesView = lazy(() => import('@/features/curves/CurvesView').then((module) => ({ default: module.CurvesView })))
const LibraryView = lazy(() => import('@/features/library/LibraryView').then((module) => ({ default: module.LibraryView })))

type ActiveView = 'experiment' | 'analysis' | 'library'

export function PanelShell() {
  const scenario = useDesignerStore((state) => state.scenario)
  const runs = useDesignerStore((state) => state.runs)
  const curves = useDesignerStore((state) => state.curves)
  const [activeView, setActiveView] = useState<ActiveView>('experiment')
  const [requestedRecipeId, setRequestedRecipeId] = useState<CurveRecipeId | undefined>()
  const [requestedBaseRunId, setRequestedBaseRunId] = useState<string | undefined>()
  const debouncedScenario = useDebouncedValue(scenario, 350)
  const health = useQuery({
    queryKey: ['health'],
    queryFn: ({ signal }) => fetchHealthStatus(signal),
    retry: false,
    staleTime: 30_000,
  })
  const catalog = useQuery({
    queryKey: ['catalog'],
    queryFn: ({ signal }) => fetchCatalog(signal),
    staleTime: Number.POSITIVE_INFINITY,
  })
  const inspection = useQuery({
    queryKey: ['scenario-inspection', debouncedScenario],
    queryFn: ({ signal }) => inspectScenario(debouncedScenario, signal),
    placeholderData: keepPreviousData,
    retry: false,
  })

  const validationIssues = [
    ...(inspection.data?.warnings ?? []),
    ...(inspection.data?.cost_estimate.warnings.map((warning) => ({
      loc: 'cost_estimate',
      msg: warning,
      severity: 'warning' as const,
    })) ?? []),
    ...(inspection.error instanceof ApiError ? inspection.error.issues : []),
  ]
  const parameterCapabilities = catalog.data?.capabilities?.parameters ?? {}
  const catalogSections = (catalog.data?.sections ?? []).map((section) => ({
    ...section,
    fields: section.fields.map((field) => ({ ...field, ...parameterCapabilities[field.key] })),
  }))
  const metricCapabilities = catalog.data?.capabilities?.metrics ?? {}
  const catalogMetrics = (catalog.data?.metrics ?? []).map((metric) => ({ ...metric, ...metricCapabilities[metric.key] }))
  const sweepableFields = catalogSections.flatMap((section) => section.fields).filter(
    (field) => field.sweepable && field.effect_status !== 'ignored' && field.effect_status !== 'unsupported',
  )
  const openAnalysis = useCallback((recipeId?: CurveRecipeId, baseRunId?: string) => {
    setRequestedRecipeId(recipeId)
    setRequestedBaseRunId(baseRunId)
    setActiveView('analysis')
  }, [])
  const navItems = [
    { id: 'experiment' as const, label: 'Diseñar', detail: runs.length ? `${runs.length} run${runs.length === 1 ? '' : 's'}` : 'Nuevo experimento', Icon: FlaskConical },
    { id: 'analysis' as const, label: 'Curvas', detail: `${curves.length} guardada${curves.length === 1 ? '' : 's'}`, Icon: LineChart },
    { id: 'library' as const, label: 'Experimentos', detail: 'Guardados y plantillas', Icon: Library },
  ]

  const healthTone = health.data?.status === 'ok' ? 'success' : health.isError ? 'danger' : 'warning'

  return (
    <main className="min-h-screen bg-background text-slate-100">
      {/* Ambient wash + faint grid: gives the dark canvas depth without adding
          a real surface that would compete with the panels. */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-x-0 top-0 h-[520px] bg-[radial-gradient(ellipse_70%_60%_at_30%_0%,rgb(var(--color-accent)/0.10),transparent_60%),radial-gradient(ellipse_60%_50%_at_80%_0%,rgb(var(--color-violet)/0.08),transparent_55%)]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 bg-grid-faint opacity-[0.35] [background-size:56px_56px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,black,transparent)]"
      />
      <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-control border border-cyan/30 bg-cyan/10 text-cyan shadow-glow">
                <RadioTower aria-hidden="true" size={19} />
              </div>
              <div>
                <p className="text-sm font-semibold tracking-tight text-white">QKD Workbench</p>
                <p className="text-2xs text-slate-500">Diseño y análisis de enlaces cuánticos</p>
              </div>
            </div>
            <HealthPill compact isError={health.isError} status={health.data?.status} tone={healthTone} />
          </div>
          <div className="flex min-w-0 items-center gap-3">
            <nav aria-label="Vistas principales" className="grid min-w-0 flex-1 grid-cols-3 gap-1 rounded-control border border-border bg-surface/80 p-1 lg:flex-none">
              {navItems.map(({ id, label, detail, Icon }) => {
                const active = activeView === id
                return (
                  <button
                    aria-current={active ? 'page' : undefined}
                    className={`relative flex min-w-0 items-center justify-center gap-2 rounded-[6px] px-3 py-2 text-left transition-all duration-200 ease-emphasis lg:min-w-36 ${
                      active
                        ? 'bg-raised text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]'
                        : 'text-slate-400 hover:bg-white/[0.03] hover:text-slate-200'
                    }`}
                    key={id}
                    onClick={() => setActiveView(id)}
                    type="button"
                  >
                    {active ? (
                      <span aria-hidden="true" className="absolute inset-x-3 -bottom-px h-px bg-gradient-to-r from-transparent via-cyan to-transparent" />
                    ) : null}
                    <Icon aria-hidden="true" className={active ? 'text-cyan' : ''} size={15} />
                    <span className="min-w-0">
                      <span className="block truncate text-xs font-medium sm:text-sm">{label}</span>
                      <span className="hidden truncate text-2xs text-slate-500 lg:block">{detail}</span>
                    </span>
                  </button>
                )
              })}
            </nav>
            <HealthPill isError={health.isError} status={health.data?.status} tone={healthTone} />
          </div>
        </div>
      </header>

      <section className="relative mx-auto min-w-0 max-w-[1600px]">
        {activeView === 'experiment' ? (
          <ExperimentWorkspace
            inspection={inspection.data}
            inspectionError={inspection.error instanceof Error ? inspection.error : null}
            isValidating={inspection.isFetching}
            apiOffline={health.isError}
            onOpenAnalysis={openAnalysis}
            sections={catalogSections}
            validationIssues={validationIssues}
          />
        ) : (
          <Suspense fallback={<div className="p-4 sm:p-6"><LoadingBlock label={`Cargando ${activeView}`} /></div>}>
            {activeView === 'analysis' ? (
              <CurvesView
                initialRecipeId={requestedRecipeId}
                initialBaseRunId={requestedBaseRunId}
                metrics={catalogMetrics}
                onBackToExperiment={() => setActiveView('experiment')}
                scenario={scenario}
                sweepableFields={sweepableFields}
              />
            ) : (
              <LibraryView onOpenExperiment={() => setActiveView('experiment')} />
            )}
          </Suspense>
        )}
      </section>
      <footer className="relative mx-auto max-w-[1600px] px-4 pb-8 pt-2 text-center text-2xs text-slate-600 sm:px-6">
        Simulador pedagógico: los resultados no constituyen una certificación de seguridad ni una prueba finite-key.
      </footer>
    </main>
  )
}

/**
 * API reachability indicator. The dot pulses only while the first probe is in
 * flight, so a steady green dot reliably means "answered", not "still asking".
 */
function HealthPill({
  status,
  isError,
  tone,
  compact = false,
}: {
  status?: string
  isError: boolean
  tone: 'success' | 'danger' | 'warning'
  compact?: boolean
}) {
  const online = status === 'ok'
  const label = online ? 'API conectada' : isError ? (compact ? 'Sin API' : 'API no disponible') : 'Conectando…'
  const toneClass = {
    success: 'border-success/30 bg-success/10 text-success',
    danger: 'border-danger/30 bg-danger/10 text-danger',
    warning: 'border-warning/30 bg-warning/10 text-warning',
  }[tone]

  return (
    <div
      className={`items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-medium ${toneClass} ${
        compact ? 'flex lg:hidden' : 'hidden lg:flex'
      }`}
    >
      <span aria-hidden="true" className="relative flex h-1.5 w-1.5">
        {!online && !isError ? (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
        ) : null}
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
      </span>
      {label}
    </div>
  )
}
