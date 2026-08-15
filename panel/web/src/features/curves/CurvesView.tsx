import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Download, FileJson, Play, Square } from 'lucide-react'

import {
  ApiError,
  cancelSweep,
  createSweep,
  estimateSweep,
  fetchSweepResult,
  fetchSweepStatus,
  type AxisRequest,
  type CatalogField,
  type CatalogMetric,
  type JobStatus,
  type JsonObject,
  type ScenarioPayload,
} from '@/api/client'
import { pollJobStatus } from '@/api/polling'
import { ApiErrorSummary, Button, EmptyState, Panel } from '@/components/ui'
import {
  type ActiveSweep,
  type CurveSnapshot,
  useDesignerStore,
} from '@/features/designer/scenarioStore'
import { inferMediumFromScenario, mediumDefinitions } from '@/features/lab/mediums'
import { cloneJson, isRecord, readTarget } from '@/features/shared/scenarioPaths'
import { isAbortError, useDebouncedValue } from '@/lib/async'
import { curveTraces, sweepSummaryRows } from '@/lib/curveData'
import {
  downloadCsv,
  downloadCurveSvg,
  downloadJson,
  safeFileName,
} from '@/lib/download'
import { formatNumber, metricRecord } from '@/lib/format'
import { CurvePlot } from '@/lib/plot'
import { downloadPlotPng } from '@/lib/plotExport'

import {
  applyCurveScenarioPatch,
  buildCurveRequest,
  curveMetricLabel,
  curveRecipes,
  isCurveRequestApplicable,
  type CurveRecipeId,
} from './recipes'

/* Chart props are intentionally memoized across polling-only updates. */
/* eslint-disable react-hooks/preserve-manual-memoization */

export function CurvesView({
  metrics,
  scenario,
  sweepableFields,
  onBackToExperiment,
  initialRecipeId,
  initialBaseRunId,
}: {
  metrics: CatalogMetric[]
  scenario: ScenarioPayload
  sweepableFields: CatalogField[]
  onBackToExperiment: () => void
  initialRecipeId?: CurveRecipeId
  initialBaseRunId?: string
}) {
  const runs = useDesignerStore((state) => state.runs)
  const curves = useDesignerStore((state) => state.curves)
  const activeSweep = useDesignerStore((state) => state.activeSweep)
  const beginSweep = useDesignerStore((state) => state.beginSweep)
  const updateSweepStatus = useDesignerStore((state) => state.updateSweepStatus)
  const finishSweep = useDesignerStore((state) => state.finishSweep)
  const clearActiveSweep = useDesignerStore((state) => state.clearActiveSweep)
  const latestRun = runs.at(-1) ?? null
  const requestedBaseRun = initialBaseRunId ? runs.find((run) => run.jobId === initialBaseRunId) ?? null : latestRun
  const initialBaseScenario = requestedBaseRun?.scenario ?? scenario
  const initialMediumId = inferMediumFromScenario(initialBaseScenario)
  const initialRecipes = curveRecipes.filter((recipe) => initialMediumId === 'custom' || recipe.preferredMedia.includes(initialMediumId))
  const defaultRecipeId = mediumDefinitions[initialMediumId].defaultCurveRecipeId
  const initialRecipe = initialRecipeId && initialRecipes.some((recipe) => recipe.id === initialRecipeId)
    ? initialRecipeId
    : initialRecipes.some((recipe) => recipe.id === defaultRecipeId)
      ? defaultRecipeId
      : initialRecipes[0]?.id ?? 'custom-axis'
  const [baseId, setBaseId] = useState(requestedBaseRun ? `run:${requestedBaseRun.jobId}` : 'draft')
  const [recipeId, setRecipeId] = useState<CurveRecipeId>(initialRecipe)
  const initialRequest = buildCurveRequest(initialRecipe, initialMediumId)
  const initialValues = rangeValues(initialRequest.axis)
  const [axisTarget, setAxisTarget] = useState(initialRequest.axis.target)
  const [metric, setMetric] = useState(initialRequest.metric)
  const [start, setStart] = useState(initialValues.start)
  const [stop, setStop] = useState(initialValues.stop)
  const [steps, setSteps] = useState(initialValues.steps)
  const [scale, setScale] = useState<'linear' | 'log'>(initialValues.scale)
  const [repeats, setRepeats] = useState(initialRequest.repeats)
  const [seriesTarget, setSeriesTarget] = useState('')
  const [seriesValues, setSeriesValues] = useState('')
  const [graphElement, setGraphElement] = useState<HTMLElement | null>(null)
  const [resumeError, setResumeError] = useState<Error | null>(null)
  const [resumeVersion, setResumeVersion] = useState(0)
  const operation = useRef<{ generation: number; controller: AbortController; jobId: string | null } | null>(null)
  const generation = useRef(0)

  useEffect(() => () => {
    generation.current += 1
    operation.current?.controller.abort()
    operation.current = null
  }, [])

  const baseRun = baseId.startsWith('run:') ? runs.find((run) => `run:${run.jobId}` === baseId) ?? latestRun : null
  const baseScenario = baseRun?.scenario ?? scenario
  const baseDigest = baseRun?.digest ?? 'draft'
  const baseLabel = baseRun ? `${baseRun.label} · ${baseRun.digest.slice(0, 10)}` : 'Draft actual'
  const baseMediumId = inferMediumFromScenario(baseScenario)
  const availableRecipes = curveRecipes.filter((recipe) => baseMediumId === 'custom' || recipe.preferredMedia.includes(baseMediumId))
  const recipeRequest = buildCurveRequest(recipeId, baseMediumId)
  const effectiveScenario = applyCurveScenarioPatch(baseScenario, recipeRequest.scenarioPatch)
  const applicableFields = sweepableFields.filter((field) => catalogFieldApplies(field, effectiveScenario))
  const availableFields = recipeRequest.axis.target === 'time_s' ? [timeAxisField, ...applicableFields] : applicableFields
  const resolvedAxisTarget = availableFields.some((field) => field.key === axisTarget)
    ? axisTarget
    : availableFields[0]?.key ?? axisTarget
  const axisField = availableFields.find((field) => field.key === resolvedAxisTarget) ?? null
  const availableMetrics = metrics.filter((item) => item.key !== 'secure' && metricApplies(item, effectiveScenario))
  const resolvedMetric = availableMetrics.some((item) => item.key === metric)
    ? metric
    : availableMetrics[0]?.key ?? metric
  const validation = validateBuilder({ start, stop, steps, repeats, scale, axisField })
  const recipeApplicability = isCurveRequestApplicable({
    ...recipeRequest,
    axis: { target: resolvedAxisTarget, values: { start, stop, steps, scale } },
    metric: resolvedMetric,
    repeats,
  }, baseScenario)
  const series = useMemo(
    () => seriesTarget ? { target: seriesTarget, values: parseSeriesValues(seriesValues) } : null,
    [seriesTarget, seriesValues],
  )
  const request = {
    scenario: effectiveScenario,
    axis: { target: resolvedAxisTarget, values: { start, stop, steps, scale } } satisfies AxisRequest,
    series,
    repeats,
  }
  const debouncedRequestJson = useDebouncedValue(JSON.stringify(request), 500)
  const debouncedRequest = JSON.parse(debouncedRequestJson) as typeof request
  const estimate = useQuery({
    queryKey: ['sweep-estimate', debouncedRequestJson],
    queryFn: ({ signal }) => estimateSweep(debouncedRequest, signal),
    enabled: validation.length === 0 && recipeApplicability.applicable,
    retry: false,
  })

  const applyRecipe = (nextId: CurveRecipeId) => {
    configureRecipe(nextId, baseScenario)
  }

  const configureRecipe = (nextId: CurveRecipeId, recipeBaseScenario: ScenarioPayload) => {
    const next = buildCurveRequest(nextId, inferMediumFromScenario(recipeBaseScenario))
    const values = rangeValues(next.axis)
    setRecipeId(nextId)
    setAxisTarget(next.axis.target)
    setMetric(next.metric)
    setStart(values.start)
    setStop(values.stop)
    setSteps(values.steps)
    setScale(values.scale)
    setRepeats(next.repeats)
    setSeriesTarget(next.series?.target ?? '')
    setSeriesValues(Array.isArray(next.series?.values) ? next.series.values.map(String).join(', ') : '')
  }

  const changeBase = (nextBaseId: string) => {
    const nextRun = nextBaseId.startsWith('run:') ? runs.find((run) => `run:${run.jobId}` === nextBaseId) ?? null : null
    const nextScenario = nextRun?.scenario ?? scenario
    const nextMediumId = inferMediumFromScenario(nextScenario)
    const nextRecipes = curveRecipes.filter((recipe) => nextMediumId === 'custom' || recipe.preferredMedia.includes(nextMediumId))
    setBaseId(nextBaseId)
    if (!nextRecipes.some((recipe) => recipe.id === recipeId)) {
      const preferredId = mediumDefinitions[nextMediumId].defaultCurveRecipeId
      const nextRecipeId = nextRecipes.some((recipe) => recipe.id === preferredId) ? preferredId : nextRecipes[0]?.id ?? 'custom-axis'
      configureRecipe(nextRecipeId, nextScenario)
    }
  }

  const sweepMutation = useMutation({
    mutationFn: async (): Promise<CurveSnapshot> => {
      operation.current?.controller.abort()
      clearActiveSweep()
      const requestGeneration = ++generation.current
      const controller = new AbortController()
      operation.current = { generation: requestGeneration, controller, jobId: null }
      const scenarioSnapshot = cloneJson(effectiveScenario)
      const finalRequest = { ...request, scenario: scenarioSnapshot }
      const created = await createSweep(finalRequest, controller.signal)
      ensureCurrentSweep(requestGeneration, generation.current)
      operation.current.jobId = created.job_id
      const active: ActiveSweep = {
        jobId: created.job_id,
        baseDigest,
        baseLabel,
        scenario: scenarioSnapshot,
        axis: finalRequest.axis,
        series: finalRequest.series,
        metric: resolvedMetric,
        repeats,
        startedAt: new Date().toISOString(),
        costEstimate: created.cost_estimate,
        status: null,
      }
      beginSweep(active)
      const status = await pollJobStatus((signal) => fetchSweepStatus(created.job_id, signal), {
        signal: controller.signal,
        onStatus: (snapshot) => {
          if (requestGeneration === generation.current) updateSweepStatus(snapshot)
        },
      })
      ensureCurrentSweep(requestGeneration, generation.current)
      const result = status.status === 'done' ? await fetchSweepResult(created.job_id, controller.signal) : null
      if (status.status !== 'done' || !result) throw new ApiError(status.error ?? `El sweep terminó con estado ${status.status}.`, 422, status.issues ?? [])
      return {
        jobId: created.job_id,
        baseDigest,
        baseLabel,
        scenario: scenarioSnapshot,
        axis: finalRequest.axis,
        series: finalRequest.series,
        metric: resolvedMetric,
        repeats,
        createdAt: new Date().toISOString(),
        result,
        costEstimate: active.costEstimate,
      }
    },
    onSuccess: (curve) => {
      finishSweep(curve)
      operation.current = null
      setResumeError(null)
    },
    onError: (error) => {
      const hasServerJob = Boolean(operation.current?.jobId || useDesignerStore.getState().activeSweep)
      operation.current = null
      if (!isAbortError(error)) {
        if (hasServerJob) setResumeError(error instanceof Error ? error : new Error('No se pudo consultar el sweep.'))
        else clearActiveSweep()
        if (hasServerJob) setResumeVersion((version) => version + 1)
      }
    },
  })

  const resumableSweepId = activeSweep && (!activeSweep.status || runningStates.has(activeSweep.status.status)) ? activeSweep.jobId : null
  useEffect(() => {
    if (!resumableSweepId || operation.current) return
    const stored = useDesignerStore.getState().activeSweep
    if (!stored || stored.jobId !== resumableSweepId) return
    const requestGeneration = ++generation.current
    const controller = new AbortController()
    operation.current = { generation: requestGeneration, controller, jobId: stored.jobId }
    const resume = async () => {
      try {
        const status = await pollJobStatus((signal) => fetchSweepStatus(stored.jobId, signal), { signal: controller.signal, onStatus: updateSweepStatus })
        ensureCurrentSweep(requestGeneration, generation.current)
        if (status.status === 'done') {
          const result = await fetchSweepResult(stored.jobId, controller.signal)
          finishSweep({
            jobId: stored.jobId,
            baseDigest: stored.baseDigest,
            baseLabel: stored.baseLabel,
            scenario: stored.scenario,
            axis: stored.axis,
            series: stored.series,
            metric: stored.metric,
            repeats: stored.repeats,
            createdAt: new Date().toISOString(),
            result,
            costEstimate: stored.costEstimate,
          })
        } else if (status.status !== 'cancelled') {
          throw new ApiError(status.error ?? `El sweep terminó con estado ${status.status}.`, 422, status.issues ?? [])
        }
      } catch (error) {
        if (!isAbortError(error)) {
          setResumeError(error instanceof Error ? error : new Error('No se pudo reanudar el sweep.'))
          if (!useDesignerStore.getState().activeSweep) clearActiveSweep()
        }
      } finally {
        if (operation.current?.generation === requestGeneration) operation.current = null
      }
    }
    void resume()
    return () => controller.abort()
  }, [clearActiveSweep, finishSweep, resumableSweepId, resumeVersion, updateSweepStatus])

  const cancel = useMutation({
    mutationFn: async () => {
      const stored = useDesignerStore.getState().activeSweep
      if (!stored) return null
      generation.current += 1
      operation.current?.controller.abort()
      operation.current = null
      return { stored, response: await cancelSweep(stored.jobId) }
    },
    onSuccess: (payload) => {
      if (!payload) return
      const status = payload.response.status ?? (payload.response.cancelled ? 'cancelled' : payload.response.cancellation_requested ? 'cancellation_requested' : payload.stored.status?.status ?? 'running')
      updateSweepStatus({ ...(payload.stored.status ?? { job_id: payload.stored.jobId, progress: { done: 0, total: 1 }, elapsed_s: 0 }), status })
      setResumeVersion((version) => version + 1)
    },
    onError: () => setResumeVersion((version) => version + 1),
  })

  const displayedCurve = curves.at(-1) ?? null
  const rows = useMemo(() => displayedCurve && Array.isArray(displayedCurve.result.rows) ? displayedCurve.result.rows.filter(isRecord) : [], [displayedCurve])
  const summaryRows = useMemo(() => displayedCurve ? sweepSummaryRows(displayedCurve.result.summary) : [], [displayedCurve])
  const displayedMetric = displayedCurve?.metric ?? resolvedMetric
  const displayedAxis = displayedCurve?.axis.target ?? resolvedAxisTarget
  const displayedSeries = displayedCurve?.series?.target ?? ''
  const plotRows = useMemo(() => summaryRows.some((row) => `${displayedMetric}_mean` in row) ? summaryRows : rows, [displayedMetric, rows, summaryRows])
  const displayedBaseRun = displayedCurve ? runs.find((run) => run.digest === displayedCurve.baseDigest) ?? null : baseRun
  const basePointX = displayedBaseRun ? finiteNumber(readTarget(displayedBaseRun.scenario, displayedAxis)) : null
  const basePointY = displayedBaseRun ? finiteNumber(metricRecord(displayedBaseRun.status.result_summary ?? {})[displayedMetric]) : null
  const traces = useMemo(() => [
    ...curveTraces(plotRows, displayedAxis, displayedMetric, displayedSeries, curveMetricLabel(displayedMetric)),
    ...(basePointX !== null && basePointY !== null ? [{
      x: [basePointX], y: [basePointY], mode: 'markers', name: 'Run de partida', type: 'scatter',
      marker: { color: '#f8fafc', line: { color: '#8b5cf6', width: 2 }, size: 11, symbol: 'diamond' },
    }] : []),
  ], [basePointX, basePointY, displayedAxis, displayedMetric, displayedSeries, plotRows])
  const status = activeSweep?.status ?? null
  const progress = status?.progress
  const progressPercent = progress && progress.total > 0 ? (100 * progress.done) / progress.total : 0
  const qberThreshold = finiteNumber(readTarget(displayedCurve?.scenario ?? effectiveScenario, 'post_processing.qber_abort_threshold'))
  const xField = sweepableFields.find((field) => field.key === displayedAxis)
  const yMetric = metrics.find((item) => item.key === displayedMetric)
  const exportPayload = displayedCurve ? {
    schema_version: 1,
    kind: 'qkd_curve',
    generated_at: displayedCurve.createdAt,
    job_id: displayedCurve.jobId,
    base_digest: displayedCurve.baseDigest,
    base_label: displayedCurve.baseLabel,
    scenario: displayedCurve.scenario,
    axis: displayedCurve.axis,
    series: displayedCurve.series,
    metric: displayedCurve.metric,
    repeats: displayedCurve.repeats,
    cost_estimate: displayedCurve.costEstimate,
    result: displayedCurve.result,
  } : null
  const chartTitle = `${yMetric?.label_es ?? curveMetricLabel(displayedMetric)} vs ${xField?.label_es ?? displayedAxis}`
  const chartXLabel = axisTitle(xField, displayedAxis)
  const chartYLabel = metricTitle(yMetric, displayedMetric)

  return (
    <div className="min-w-0 space-y-5 p-4 sm:p-6">
      <header className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <button className="mb-2 flex items-center gap-1 text-xs text-slate-500 hover:text-cyan" onClick={onBackToExperiment} type="button"><ArrowLeft aria-hidden="true" size={13} /> Volver al experimento</button>
          <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-cyan">Estudio visual</p>
          <h1 className="mt-1 text-xl font-semibold text-white">Análisis y curvas</h1>
          <p className="mt-1 text-sm text-slate-400">Cada curva conserva un run o draft como punto de partida reproducible.</p>
        </div>
        <p className="font-mono text-xs text-slate-500">{curves.length} curva{curves.length === 1 ? '' : 's'} guardada{curves.length === 1 ? '' : 's'} en el experimento</p>
      </header>

      <div className="grid min-w-0 gap-5 xl:grid-cols-[420px_minmax(0,1fr)]">
        <Panel className="min-w-0 p-4">
          <h2 className="text-sm font-semibold text-white">¿Qué quieres estudiar?</h2>
          <div className="mt-4 space-y-4">
            <div className="rounded-xl border border-violet-400/30 bg-violet-400/5 p-3">
              <p className="text-xs font-semibold uppercase tracking-[0.08em] text-violet-300">Este run es el punto de partida</p>
              <SelectField label="Escenario base" onChange={changeBase} options={[{ value: 'draft', label: 'Draft actual' }, ...runs.map((run) => ({ value: `run:${run.jobId}`, label: `${run.label} · ${run.digest.slice(0, 8)}` }))]} value={baseId} />
              <p className="mt-2 text-xs leading-5 text-slate-400">El snapshot no se modifica. Una curva necesita calcular nuevos puntos variando sólo el eje elegido; el resto de sus ajustes permanece fijo.</p>
            </div>
            <div className="grid max-h-72 gap-2 overflow-y-auto pr-1 sm:grid-cols-2 xl:grid-cols-1">
              {availableRecipes.map((recipe) => (
                <button
                  aria-pressed={recipe.id === recipeId}
                  className={`rounded-xl border px-3 py-3 text-left transition ${recipe.id === recipeId ? 'border-cyan/70 bg-cyan/10 text-white' : 'border-border bg-background/45 text-slate-300 hover:border-slate-500 hover:bg-raised'}`}
                  key={recipe.id}
                  onClick={() => applyRecipe(recipe.id)}
                  type="button"
                >
                  <span className="block text-sm font-medium">{recipe.label}</span>
                  <span className="mt-1 block text-[11px] leading-4 text-slate-500">{recipe.question}</span>
                </button>
              ))}
            </div>
            <div className="rounded-xl border border-cyan/20 bg-cyan/5 p-3">
              <p className="text-sm text-slate-200">
                Variar <b>{axisField?.label_es ?? resolvedAxisTarget}</b> de <span className="font-mono">{start}</span> a <span className="font-mono">{stop}</span> en {steps} puntos.
              </p>
              <p className="mt-1 text-xs text-slate-500">Dibujar {curveMetricLabel(resolvedMetric)} · {repeats} repetición{repeats === 1 ? '' : 'es'}.</p>
            </div>
            <details className="group rounded-xl border border-border bg-background/35 p-3">
              <summary className="cursor-pointer text-sm font-medium text-slate-300 hover:text-white">Personalizar rango, métrica y series</summary>
              <div className="mt-4 space-y-4 border-t border-border pt-4">
            <SelectField label="Receta guiada" onChange={(value) => applyRecipe(value as CurveRecipeId)} options={availableRecipes.map((recipe) => ({ value: recipe.id, label: recipe.label }))} value={recipeId} />
            <RecipeDisclosure recipeId={recipeId} mediumId={inferMediumFromScenario(baseScenario)} scenario={baseScenario} />
            <SelectField label="2. Parámetro X" onChange={setAxisTarget} options={availableFields.map((field) => ({ value: field.key, label: fieldOptionLabel(field, effectiveScenario) }))} value={resolvedAxisTarget} />
            {axisField ? <AxisDescription field={axisField} scenario={effectiveScenario} /> : null}
            <SelectField label="3. Métrica Y" onChange={setMetric} options={availableMetrics.map((item) => ({ value: item.key, label: `${item.label_es}${item.unit ? ` [${item.unit}]` : ''}` }))} value={resolvedMetric} />
            <fieldset>
              <legend className="text-xs text-slate-500">4. Rango y puntos</legend>
              <div className="mt-1 grid grid-cols-2 gap-2">
                <NumberField label="Inicio" onChange={setStart} value={start} />
                <NumberField label="Fin" onChange={setStop} value={stop} />
                <NumberField integer label="Puntos" max={101} min={2} onChange={setSteps} value={steps} />
                <SelectField label="Escala" onChange={(value) => setScale(value as 'linear' | 'log')} options={[{ value: 'linear', label: 'Lineal' }, { value: 'log', label: 'Logarítmica' }]} value={scale} />
              </div>
            </fieldset>
            <fieldset>
              <legend className="text-xs text-slate-500">5. Serie opcional</legend>
              <div className="mt-1 space-y-2">
                <SelectField label="Parámetro de serie" onChange={setSeriesTarget} options={[{ value: '', label: 'Sin serie' }, ...availableFields.filter((field) => field.key !== resolvedAxisTarget).map((field) => ({ value: field.key, label: field.label_es }))]} value={seriesTarget} />
                <label className="block"><span className="text-xs text-slate-500">Valores separados por comas</span><input className={inputClass} disabled={!seriesTarget} onChange={(event) => setSeriesValues(event.target.value)} placeholder="0.6, 0.8, 0.95" value={seriesValues} /></label>
              </div>
            </fieldset>
            <NumberField integer label="6. Repeticiones" max={50} min={1} onChange={setRepeats} value={repeats} />
              </div>
            </details>
            {validation.map((message) => <p className="text-xs text-danger" key={message}>{message}</p>)}
            {!recipeApplicability.applicable ? <p className="text-xs text-warning">{recipeApplicability.reasons.join(' ')}</p> : null}
            <div className="border-y border-border py-3 text-xs">
              <div className="flex items-center justify-between gap-3"><span className="text-slate-500">Ejecuciones</span><span className="font-mono text-slate-200">{steps * repeats * Math.max(1, series?.values.length ?? 1)}</span></div>
              <div className="mt-1 flex items-center justify-between gap-3"><span className="text-slate-500">Cota estimada</span><span className="font-mono text-slate-200">{estimate.data ? `${estimate.data.total_pulse_events.toLocaleString('es-ES')} pulsos` : estimate.isFetching ? 'calculando…' : 'no disponible'}</span></div>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button className="flex-1" disabled={sweepMutation.isPending || validation.length > 0 || !recipeApplicability.applicable || Boolean(activeSweep && runningStates.has(activeSweep.status?.status ?? 'queued'))} onClick={() => sweepMutation.mutate()} tone="primary" type="button"><Play aria-hidden="true" size={15} /> Generar curva · {steps} puntos</Button>
              <Button disabled={!activeSweep || !runningStates.has(activeSweep.status?.status ?? 'queued')} onClick={() => cancel.mutate()} tone="warning" type="button"><Square aria-hidden="true" size={14} /> Cancelar</Button>
            </div>
            {status ? <div aria-live="polite"><div className="flex justify-between text-xs text-slate-400"><span>{statusLabel(status.status)}</span><span>{status.progress.done}/{status.progress.total}</span></div><div className="mt-2 h-1.5 bg-background" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progressPercent)}><div className="h-full bg-cyan" style={{ width: `${progressPercent}%` }} /></div></div> : null}
            {sweepMutation.error && !isAbortError(sweepMutation.error) ? <ApiErrorSummary error={sweepMutation.error} /> : null}
            {estimate.error instanceof Error ? <ApiErrorSummary error={estimate.error} /> : null}
            {resumeError ? <ApiErrorSummary error={resumeError} /> : null}
          </div>
        </Panel>

        <div className="min-w-0 space-y-5">
          <Panel className="min-w-0 overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-sm font-semibold text-white">{displayedCurve ? `${curveMetricLabel(displayedMetric)} frente a ${xField?.label_es ?? displayedAxis}` : 'Curva del experimento'}</h2>
                <p className="mt-1 text-xs text-slate-500">{displayedCurve ? `${displayedCurve.baseLabel} · ${displayedCurve.repeats} repetición${displayedCurve.repeats === 1 ? '' : 'es'} · job ${displayedCurve.jobId}` : 'Elige una receta y genera los puntos de la curva.'}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button disabled={!rows.length} onClick={() => downloadCsv(rows, `${safeFileName(displayedMetric)}-vs-${safeFileName(displayedAxis)}.csv`)} size="sm" tone="neutral" type="button"><Download aria-hidden="true" size={13} /> CSV</Button>
                <Button disabled={!rows.length} onClick={() => downloadCurveSvg(rows, displayedAxis, displayedMetric, { xLabel: xField?.label_es ?? displayedAxis, xUnit: xField?.unit ?? null, yLabel: yMetric?.label_es ?? displayedMetric, yUnit: yMetric?.unit ?? null })} size="sm" tone="neutral" type="button"><Download aria-hidden="true" size={13} /> SVG</Button>
                <Button disabled={!graphElement || !rows.length} onClick={() => graphElement && void downloadPlotPng(graphElement, `${safeFileName(displayedMetric)}-vs-${safeFileName(displayedAxis)}.png`)} size="sm" tone="neutral" type="button"><Download aria-hidden="true" size={13} /> PNG</Button>
                <Button disabled={!exportPayload} onClick={() => exportPayload && downloadJson(`${safeFileName(displayedMetric)}-sweep.json`, exportPayload)} size="sm" tone="neutral" type="button"><FileJson aria-hidden="true" size={13} /> JSON</Button>
              </div>
            </div>
            {rows.length ? (
              <div className="h-[430px] min-w-0 p-2" ref={setGraphElement}>
                <CurvePlot traces={traces} title={chartTitle} xLabel={chartXLabel} yLabel={chartYLabel} threshold={displayedMetric === 'qber' ? qberThreshold : null} />
              </div>
            ) : <div className="p-4"><EmptyState description="La gráfica mostrará valores finitos, bandas p05–p95 cuando haya repeticiones, el run de partida y el umbral QBER si procede." title="Aún no hay puntos calculados" /></div>}
          </Panel>
          {displayedCurve ? <CurveSummary curve={displayedCurve} rows={plotRows} /> : null}
          {rows.length ? <AccessibleCurveTable axisKey={displayedAxis} metricKey={displayedMetric} rows={plotRows} seriesKey={displayedSeries} /> : null}
        </div>
      </div>
    </div>
  )
}

const inputClass = 'mt-1 h-9 w-full rounded-control border border-border bg-background px-3 font-mono text-xs text-white focus:border-cyan disabled:opacity-40'
const runningStates = new Set<JobStatus['status']>(['queued', 'running', 'cancellation_requested'])

function SelectField({ label, options, value, onChange }: { label: string; options: Array<{ value: string; label: string }>; value: string; onChange: (value: string) => void }) {
  return <label className="block"><span className="text-xs text-slate-500">{label}</span><select className={inputClass} onChange={(event) => onChange(event.target.value)} value={value}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
}

function NumberField({ label, value, min, max, integer = false, onChange }: { label: string; value: number; min?: number; max?: number; integer?: boolean; onChange: (value: number) => void }) {
  return <label className="block"><span className="text-xs text-slate-500">{label}</span><input className={inputClass} max={max} min={min} onChange={(event) => onChange(integer ? Math.round(Number(event.target.value)) : Number(event.target.value))} step={integer ? 1 : 'any'} type="number" value={Number.isFinite(value) ? value : 0} /></label>
}

function AxisDescription({ field, scenario }: { field: CatalogField; scenario: ScenarioPayload }) {
  return <div className="border-l-2 border-cyan/40 bg-background/50 px-3 py-2 text-xs"><p className="text-slate-300">Actual <span className="font-mono text-white">{String(readTarget(scenario, field.key) ?? '—')} {field.unit ?? ''}</span></p><p className="mt-1 text-slate-500">Rango razonable {field.min ?? '−∞'}–{field.max ?? '∞'} {field.unit ?? ''} · escala {field.scale ?? 'lineal'} · bloque {field.key.split('.')[0]}</p>{field.effect_reason ? <p className="mt-1 text-warning">{field.effect_reason}</p> : null}</div>
}

function RecipeDisclosure({ recipeId, mediumId, scenario }: { recipeId: CurveRecipeId; mediumId: ReturnType<typeof inferMediumFromScenario>; scenario: ScenarioPayload }) {
  const request = buildCurveRequest(recipeId, mediumId)
  const applicability = isCurveRequestApplicable(request, scenario)
  return <details className="group border-l-2 border-border bg-background/40 px-3 py-2 text-xs"><summary className="cursor-pointer text-slate-300">Qué modifica esta receta</summary><dl className="mt-2 space-y-1 text-slate-500"><div><dt className="inline">Escenario: </dt><dd className="inline text-slate-300">{request.scenarioPatch ? 'aplica un ajuste explícito' : 'sin cambios'}</dd></div><div><dt className="inline">Varía: </dt><dd className="inline text-slate-300">{request.changes.join(', ') || request.axis.target}</dd></div><div><dt className="inline">Dibuja: </dt><dd className="inline text-slate-300">{curveMetricLabel(request.metric)}</dd></div><div><dt className="inline">Fijo: </dt><dd className="inline text-slate-300">{request.fixed.join(', ') || 'resto del escenario'}</dd></div><div><dt className="inline">Dinámica: </dt><dd className="inline text-slate-300">{request.axis.target === 'time_s' ? 'sí, requiere variación física' : 'no'}</dd></div></dl><p className={`mt-2 ${applicability.applicable ? 'text-success' : 'text-warning'}`}>{applicability.applicable ? 'Compatible con el escenario base.' : applicability.reasons.join(' ')}</p></details>
}

function CurveSummary({ curve, rows }: { curve: CurveSnapshot; rows: JsonObject[] }) {
  const first = rows.find((row) => finiteNumber(row[curve.metric]) !== null || finiteNumber(row[`${curve.metric}_mean`]) !== null)
  const last = [...rows].reverse().find((row) => finiteNumber(row[curve.metric]) !== null || finiteNumber(row[`${curve.metric}_mean`]) !== null)
  const firstValue = first ? finiteNumber(first[`${curve.metric}_mean`] ?? first[curve.metric]) : null
  const lastValue = last ? finiteNumber(last[`${curve.metric}_mean`] ?? last[curve.metric]) : null
  return <Panel className="p-4"><h2 className="text-sm font-semibold text-white">Resumen descriptivo</h2><p className="mt-2 text-sm leading-6 text-slate-300">{firstValue === null || lastValue === null ? 'No hay suficientes valores finitos para resumir la serie.' : `En los puntos calculados, ${curveMetricLabel(curve.metric)} pasa de ${formatNumber(firstValue)} a ${formatNumber(lastValue)}. Esta variación describe el modelo simulado; no demuestra causalidad ni seguridad operacional.`}</p><p className="mt-2 text-xs text-slate-500">Procedencia: {curve.baseLabel} · {curve.repeats} repetición{curve.repeats === 1 ? '' : 'es'} · semillas disponibles en los datos exportados.</p></Panel>
}

export function AccessibleCurveTable({ rows, axisKey, metricKey, seriesKey }: { rows: JsonObject[]; axisKey: string; metricKey: string; seriesKey: string }) {
  const [page, setPage] = useState(0)
  const pageSize = 256
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const metricValue = (row: JsonObject) => row[`${metricKey}_mean`] ?? row[metricKey]
  const safePage = Math.min(page, pageCount - 1)
  const visibleRows = rows.slice(safePage * pageSize, (safePage + 1) * pageSize)
  return <details className="rounded-panel border border-border bg-surface"><summary className="cursor-pointer px-4 py-3 text-sm font-medium text-slate-300">Datos accesibles de la curva ({rows.length} filas; pagina {safePage + 1}/{pageCount})</summary><div className="max-h-80 overflow-auto border-t border-border"><table className="w-full min-w-[520px] text-left text-xs"><thead className="sticky top-0 bg-raised text-slate-400"><tr><th className="px-3 py-2">{axisKey}</th>{seriesKey ? <th className="px-3 py-2">{seriesKey}</th> : null}<th className="px-3 py-2">{metricKey}</th><th className="px-3 py-2">p05</th><th className="px-3 py-2">p95</th></tr></thead><tbody className="divide-y divide-border">{visibleRows.map((row, index) => <tr key={`${String(row[axisKey])}-${safePage * pageSize + index}`}><td className="px-3 py-2 font-mono">{String(row[axisKey] ?? '—')}</td>{seriesKey ? <td className="px-3 py-2 font-mono">{String(row[seriesKey] ?? '—')}</td> : null}<td className="px-3 py-2 font-mono">{String(metricValue(row) ?? '—')}</td><td className="px-3 py-2 font-mono">{String(row[`${metricKey}_p05`] ?? '—')}</td><td className="px-3 py-2 font-mono">{String(row[`${metricKey}_p95`] ?? '—')}</td></tr>)}</tbody></table></div>{pageCount > 1 ? <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-slate-400"><span>Mostrando {safePage * pageSize + 1}-{Math.min(rows.length, (safePage + 1) * pageSize)} de {rows.length}</span><span className="flex gap-2"><Button disabled={safePage === 0} onClick={() => setPage((value) => Math.max(0, value - 1))} size="sm" tone="neutral" type="button">Anterior</Button><Button disabled={safePage + 1 >= pageCount} onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} size="sm" tone="neutral" type="button">Siguiente</Button></span></div> : null}</details>
}

function validateBuilder({ start, stop, steps, repeats, scale, axisField }: { start: number; stop: number; steps: number; repeats: number; scale: 'linear' | 'log'; axisField: CatalogField | null }): string[] {
  const issues: string[] = []
  if (!axisField) issues.push('Elige un parámetro X efectivo y compatible.')
  if (!Number.isFinite(start) || !Number.isFinite(stop) || stop <= start) issues.push('El fin del rango debe ser mayor que el inicio.')
  if (scale === 'log' && start <= 0) issues.push('La escala logarítmica requiere un inicio mayor que cero.')
  if (!Number.isInteger(steps) || steps < 2 || steps > 101) issues.push('Usa entre 2 y 101 puntos.')
  if (!Number.isInteger(repeats) || repeats < 1 || repeats > 50) issues.push('Usa entre 1 y 50 repeticiones.')
  if (axisField?.min != null && start < axisField.min) issues.push(`El inicio está por debajo del mínimo ${axisField.min}.`)
  if (axisField?.max != null && stop > axisField.max) issues.push(`El fin supera el máximo ${axisField.max}.`)
  return issues
}

const timeAxisField: CatalogField = {
  key: 'time_s',
  label_es: 'Tiempo de evaluación',
  type: 'number',
  unit: 's',
  default: 0,
  min: 0,
  sweepable: true,
  dynamic: true,
  effect_status: 'active',
  effect_reason: 'Muestrea una agenda dinámica física dentro de la ventana temporal.',
}

function catalogFieldApplies(field: CatalogField, scenario: ScenarioPayload): boolean {
  return field.effect_status !== 'ignored' && field.effect_status !== 'unsupported' && includesScenarioValue(field.applicable_protocols, scenario.protocol.name) && includesScenarioValue(field.applicable_source_kinds, scenario.source.kind) && includesScenarioValue(field.applicable_channel_kinds, scenario.channel.kind)
}

function metricApplies(metric: CatalogMetric, scenario: ScenarioPayload): boolean {
  return includesScenarioValue(metric.applicable_protocols, scenario.protocol.name)
}

function includesScenarioValue(allowed: string[] | undefined, value: string): boolean {
  return !allowed?.length || allowed.includes(value)
}

function parseSeriesValues(value: string): Array<number | string | boolean | null> {
  return value.split(',').map((part) => part.trim()).filter(Boolean).map((part) => part === 'true' ? true : part === 'false' ? false : part === 'null' ? null : Number.isFinite(Number(part)) ? Number(part) : part)
}

function rangeValues(axis: AxisRequest): { start: number; stop: number; steps: number; scale: 'linear' | 'log' } {
  if (!Array.isArray(axis.values)) return { start: axis.values.start, stop: axis.values.stop, steps: axis.values.steps, scale: axis.values.scale ?? 'linear' }
  const numeric = axis.values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  return { start: numeric[0] ?? 0, stop: numeric.at(-1) ?? 1, steps: Math.max(2, numeric.length), scale: 'linear' }
}

function fieldOptionLabel(field: CatalogField, scenario: ScenarioPayload): string {
  return `${field.label_es}${field.unit ? ` [${field.unit}]` : ''} · actual ${String(readTarget(scenario, field.key) ?? '—')}`
}

function axisTitle(field: CatalogField | undefined, fallback: string): string {
  return `${field?.label_es ?? fallback}${field?.unit ? ` [${field.unit}]` : ''}`
}

function metricTitle(metric: CatalogMetric | undefined, fallback: string): string {
  return `${metric?.label_es ?? curveMetricLabel(fallback)}${metric?.unit ? ` [${metric.unit}]` : ''}`
}

function statusLabel(status: JobStatus['status']): string {
  const labels: { [key in JobStatus['status']]: string } = { queued: 'En cola', running: 'Calculando curva', cancellation_requested: 'Cancelación solicitada', cancelled: 'Cancelado', timed_out: 'Tiempo agotado', done: 'Completado', error: 'Error', interrupted: 'Interrumpido al reiniciar', expired: 'Expirado' }
  return labels[status]
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function ensureCurrentSweep(expected: number, current: number): void {
  if (expected !== current) throw new DOMException('Stale sweep response', 'AbortError')
}
