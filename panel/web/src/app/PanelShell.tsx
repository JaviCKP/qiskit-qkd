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

  return (
    <main className="min-h-screen bg-background text-slate-100">
      <div aria-hidden="true" className="pointer-events-none fixed inset-x-0 top-0 h-[420px] bg-[radial-gradient(circle_at_35%_0%,rgba(47,200,222,0.10),transparent_42%),radial-gradient(circle_at_75%_0%,rgba(167,139,250,0.08),transparent_36%)]" />
      <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-cyan/30 bg-cyan/10 text-cyan shadow-[0_0_24px_rgba(47,200,222,0.10)]">
                <RadioTower aria-hidden="true" size={19} />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">QKD Workbench</p>
                <p className="text-[11px] text-slate-500">Diseño y análisis de enlaces cuánticos</p>
              </div>
            </div>
            <div className={`flex items-center gap-1.5 text-[11px] lg:hidden ${health.data?.status === 'ok' ? 'text-success' : health.isError ? 'text-danger' : 'text-warning'}`}>
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
              {health.data?.status === 'ok' ? 'API conectada' : health.isError ? 'Sin API' : 'Conectando…'}
            </div>
          </div>
          <div className="flex min-w-0 items-center gap-3">
            <nav aria-label="Vistas principales" className="grid min-w-0 flex-1 grid-cols-3 rounded-xl border border-border bg-surface/70 p-1 lg:flex-none">
              {navItems.map(({ id, label, detail, Icon }) => (
                <button
                  aria-current={activeView === id ? 'page' : undefined}
                  className={`flex min-w-0 items-center justify-center gap-2 rounded-lg px-3 py-2 text-left transition-colors lg:min-w-36 ${activeView === id ? 'bg-raised text-white shadow-sm' : 'text-slate-400 hover:text-white'}`}
                  key={id}
                  onClick={() => setActiveView(id)}
                  type="button"
                >
                  <Icon aria-hidden="true" className={activeView === id ? 'text-cyan' : ''} size={15} />
                  <span className="min-w-0">
                    <span className="block truncate text-xs font-medium sm:text-sm">{label}</span>
                    <span className="hidden truncate text-[10px] text-slate-500 lg:block">{detail}</span>
                  </span>
                </button>
              ))}
            </nav>
            <div className={`hidden items-center gap-1.5 text-[11px] lg:flex ${health.data?.status === 'ok' ? 'text-success' : health.isError ? 'text-danger' : 'text-warning'}`}>
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />
              {health.data?.status === 'ok' ? 'API conectada' : health.isError ? 'API no disponible' : 'Conectando…'}
            </div>
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
      <footer className="relative mx-auto max-w-[1600px] px-4 pb-8 pt-2 text-center text-[11px] text-slate-600 sm:px-6">
        Simulador pedagógico: los resultados no constituyen una certificación de seguridad ni una prueba finite-key.
      </footer>
    </main>
  )
}
