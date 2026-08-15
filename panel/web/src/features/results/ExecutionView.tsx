import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, Database, Download, Play, Square } from 'lucide-react'

import {
  ApiError,
  cancelRun,
  type CostEstimate,
  createRun,
  fetchRunResult,
  fetchRunStatus,
  type JobStatus,
  type JsonObject,
  type ScenarioPayload,
} from '@/api/client'
import { pollJobStatus } from '@/api/polling'
import { ApiErrorSummary, Button, ConfirmPanel, Dialog, EmptyState, InfoTip, StatusBadge } from '@/components/ui'
import {
  type ActiveRun,
  type RunSnapshot,
  useDesignerStore,
} from '@/features/designer/scenarioStore'
import { fieldHelp } from '@/features/experiment/fieldHelp'
import { cloneJson, isRecord } from '@/features/shared/scenarioPaths'
import { isAbortError } from '@/lib/async'
import { downloadCsv, downloadJson, safeFileName } from '@/lib/download'
import { formatNumber, metricRecord } from '@/lib/format'

import {
  resultPresentation,
  visibleResultTabs,
  type ResultPresentation,
  type ResultTab,
} from './resultSemantics'
import {
  ClassicalResultView,
  DecoyResultView,
  GenericStructuredResultView,
  ProvenanceResultView,
  SummaryDataView,
} from './StructuredResultViews'

export type { RunSnapshot } from '@/features/designer/scenarioStore'

const runningStates = new Set<JobStatus['status']>(['queued', 'running', 'cancellation_requested'])

export function ExecutionView({
  scenario,
  costEstimate,
  currentDigest,
  validationBlocked = false,
  apiOffline = false,
}: {
  scenario: ScenarioPayload
  costEstimate?: CostEstimate
  currentDigest?: string | null
  validationBlocked?: boolean
  apiOffline?: boolean
}) {
  const [label, setLabel] = useState('Ejecución principal')
  const [confirming, setConfirming] = useState(false)
  const [blockedAttempt, setBlockedAttempt] = useState(false)
  const [resumeVersion, setResumeVersion] = useState(0)
  const [resumeError, setResumeError] = useState<Error | null>(null)
  const [hydrationError, setHydrationError] = useState<Error | null>(null)
  const runs = useDesignerStore((state) => state.runs)
  const activeRun = useDesignerStore((state) => state.activeRun)
  const beginRun = useDesignerStore((state) => state.beginRun)
  const updateRunStatus = useDesignerStore((state) => state.updateRunStatus)
  const finishRun = useDesignerStore((state) => state.finishRun)
  const hydrateRunResult = useDesignerStore((state) => state.hydrateRunResult)
  const clearActiveRun = useDesignerStore((state) => state.clearActiveRun)
  const updateField = useDesignerStore((state) => state.updateField)
  const latestRun = runs.at(-1) ?? null
  const previousRun = runs.length > 1 ? runs.at(-2) ?? null : null
  const operation = useRef<{ generation: number; controller: AbortController; jobId: string | null } | null>(null)
  const generation = useRef(0)
  const requestRunRef = useRef<() => void>(() => undefined)

  useEffect(() => () => {
    generation.current += 1
    operation.current?.controller.abort()
    operation.current = null
  }, [])

  const latestRunNeedsHydration = Boolean(
    latestRun && Object.keys(latestRun.result).length === 0,
  )
  useEffect(() => {
    if (!latestRun || !latestRunNeedsHydration) return undefined
    const controller = new AbortController()
    void fetchRunResult(latestRun.jobId, controller.signal)
      .then((result) => {
        setHydrationError(null)
        hydrateRunResult(latestRun.jobId, result)
      })
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          setHydrationError(error instanceof Error ? error : new Error('No se pudo recuperar el resultado persistido.'))
        }
      })
    return () => controller.abort()
  }, [hydrateRunResult, latestRun, latestRunNeedsHydration])

  useEffect(() => {
    const handleExternalRun = () => requestRunRef.current()
    window.addEventListener('qkd:request-run', handleExternalRun)
    return () => window.removeEventListener('qkd:request-run', handleExternalRun)
  }, [])

  const runMutation = useMutation({
    mutationFn: async (): Promise<RunSnapshot> => {
      operation.current?.controller.abort()
      clearActiveRun()
      const requestGeneration = ++generation.current
      const controller = new AbortController()
      const scenarioSnapshot = cloneJson(scenario)
      const startedAt = new Date().toISOString()
      operation.current = { generation: requestGeneration, controller, jobId: null }
      const created = await createRun(scenarioSnapshot, label.trim() || 'Ejecución', controller.signal)
      ensureCurrentGeneration(requestGeneration, generation.current)
      operation.current.jobId = created.job_id
      const active: ActiveRun = {
        jobId: created.job_id,
        label: label.trim() || 'Ejecución',
        digest: created.digest,
        scenario: scenarioSnapshot,
        startedAt,
        costEstimate: created.cost_estimate,
        status: null,
      }
      beginRun(active)
      const status = await pollJobStatus((signal) => fetchRunStatus(created.job_id, signal), {
        signal: controller.signal,
        onStatus: (snapshot) => {
          if (requestGeneration === generation.current) updateRunStatus(snapshot)
        },
      })
      ensureCurrentGeneration(requestGeneration, generation.current)
      if (status.status !== 'done') {
        throw new ApiError(status.error ?? `La ejecución terminó con estado ${status.status}.`, 422, status.issues ?? [])
      }
      const result = await fetchRunResult(created.job_id, controller.signal)
      ensureCurrentGeneration(requestGeneration, generation.current)
      return {
        jobId: created.job_id,
        label: active.label,
        digest: created.digest,
        scenario: scenarioSnapshot,
        seed: scenarioSnapshot.seed,
        startedAt,
        completedAt: new Date().toISOString(),
        status,
        result,
        costEstimate: active.costEstimate,
      }
    },
    onSuccess: (snapshot) => {
      finishRun(snapshot)
      operation.current = null
      setResumeError(null)
    },
    onError: (error) => {
      const hasServerJob = Boolean(operation.current?.jobId || useDesignerStore.getState().activeRun)
      operation.current = null
      if (!isAbortError(error)) {
        if (hasServerJob) setResumeError(error instanceof Error ? error : new Error('No se pudo consultar el run.'))
        else clearActiveRun()
        if (hasServerJob) setResumeVersion((version) => version + 1)
      }
    },
  })

  const resumableRunId = activeRun && (!activeRun.status || runningStates.has(activeRun.status.status)) ? activeRun.jobId : null
  useEffect(() => {
    if (!resumableRunId || operation.current) return
    const stored = useDesignerStore.getState().activeRun
    if (!stored || stored.jobId !== resumableRunId) return
    const requestGeneration = ++generation.current
    const controller = new AbortController()
    operation.current = { generation: requestGeneration, controller, jobId: stored.jobId }
    const resume = async () => {
      try {
        const status = await pollJobStatus((signal) => fetchRunStatus(stored.jobId, signal), {
          signal: controller.signal,
          onStatus: updateRunStatus,
        })
        ensureCurrentGeneration(requestGeneration, generation.current)
        if (status.status !== 'done') {
          if (status.status === 'cancelled') return
          throw new ApiError(status.error ?? `La ejecución terminó con estado ${status.status}.`, 422, status.issues ?? [])
        }
        const result = await fetchRunResult(stored.jobId, controller.signal)
        ensureCurrentGeneration(requestGeneration, generation.current)
        finishRun({
          jobId: stored.jobId,
          label: stored.label,
          digest: stored.digest,
          scenario: stored.scenario,
          seed: stored.scenario.seed,
          startedAt: stored.startedAt,
          completedAt: new Date().toISOString(),
          status,
          result,
          costEstimate: stored.costEstimate,
        })
      } catch (error) {
        if (!isAbortError(error)) {
          setResumeError(error instanceof Error ? error : new Error('No se pudo reanudar la ejecución.'))
          // A status GET may fail after the backend accepted the job.  Keep
          // the job id so a later mount/visibility change can resume it.
          if (!useDesignerStore.getState().activeRun) clearActiveRun()
        }
      } finally {
        if (operation.current?.generation === requestGeneration) operation.current = null
      }
    }
    void resume()
    return () => controller.abort()
  }, [clearActiveRun, finishRun, resumableRunId, resumeVersion, updateRunStatus])

  const cancelMutation = useMutation({
    mutationFn: async () => {
      const current = useDesignerStore.getState().activeRun
      if (!current) return null
      generation.current += 1
      operation.current?.controller.abort()
      operation.current = null
      const response = await cancelRun(current.jobId)
      return { current, response }
    },
    onSuccess: (payload) => {
      if (!payload) return
      const status = payload.response.status ?? (payload.response.cancelled ? 'cancelled' : payload.response.cancellation_requested ? 'cancellation_requested' : payload.current.status?.status ?? 'running')
      updateRunStatus({
        ...(payload.current.status ?? {
          job_id: payload.current.jobId,
          progress: { done: 0, total: 1 },
          elapsed_s: 0,
        }),
        status,
      })
      setResumeVersion((version) => version + 1)
    },
    onError: () => {
      // The cancellation request may fail after the local poll was aborted.
      // Resume monitoring so the run never becomes stranded in the UI.
      setResumeVersion((version) => version + 1)
    },
  })

  const displayedStatus = activeRun?.status ?? null
  const progress = displayedStatus?.progress
  const progressPercent = progress && progress.total > 0 ? (100 * progress.done) / progress.total : 0
  const draftChanged = Boolean(latestRun && currentDigest && latestRun.digest !== currentDigest)
  const requiresConfirmation = Boolean(costEstimate && (costEstimate.total_pulse_events >= 1_000_000 || costEstimate.warnings.length > 0))
  const requestRun = useCallback(() => {
    setResumeError(null)
    if (validationBlocked || apiOffline) {
      setBlockedAttempt(true)
      return
    }
    setBlockedAttempt(false)
    if (requiresConfirmation) setConfirming(true)
    else runMutation.mutate()
  }, [apiOffline, requiresConfirmation, runMutation, validationBlocked])
  useEffect(() => {
    requestRunRef.current = requestRun
  }, [requestRun])
  const runIsActive = Boolean(activeRun && runningStates.has(activeRun.status?.status ?? 'queued'))
  const runButtonLabel = runMutation.isPending ? 'Preparando…' : runIsActive ? 'Ejecutando…' : 'Ejecutar experimento'

  return (
    <section aria-labelledby="execution-title" className="overflow-hidden rounded-panel border border-border bg-surface">
      <div className="border-b border-border px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">Paso 3</p>
            <h2 className="mt-1 text-base font-semibold text-white" id="execution-title">Ejecutar experimento</h2>
            <p className="mt-1 text-sm text-slate-400">La ejecución congela un snapshot; el draft seguirá siendo editable.</p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="block min-w-0 sm:w-64">
              <span className="flex items-center gap-1 text-xs text-slate-500">Etiqueta del run <InfoTip label="Etiqueta del run" text="Es el nombre con el que identificarás este snapshot en resultados y curvas." /></span>
              <input className="mt-1 h-10 w-full rounded-control border border-border bg-background px-3 text-sm text-white focus:border-cyan" maxLength={120} onChange={(event) => setLabel(event.target.value)} value={label} />
            </label>
            <Button disabled={apiOffline || runMutation.isPending || runIsActive} onClick={requestRun} tone="primary" type="button">
              <Play aria-hidden="true" size={16} /> {runButtonLabel}
            </Button>
            <Button disabled={!activeRun || !runningStates.has(activeRun.status?.status ?? 'queued') || cancelMutation.isPending} onClick={() => cancelMutation.mutate()} tone="warning" type="button">
              <Square aria-hidden="true" size={15} /> Cancelar
            </Button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 rounded-xl border border-border bg-background/55 p-3 sm:grid-cols-2 xl:grid-cols-[0.9fr_0.9fr_0.9fr_1.45fr]">
          <label className="block">
            <span className="flex items-center gap-1 text-xs font-medium text-slate-300">Señales / pulsos <InfoTip label="Señales / pulsos" text={fieldHelp('scenario.pulses')} /></span>
            <input
              aria-label="Señales / pulsos"
              className="mt-1.5 h-10 w-full rounded-lg border border-border bg-surface px-3 font-mono text-sm text-white focus:border-cyan"
              min={1}
              onChange={(event) => updateField('scenario.pulses', Number(event.target.value))}
              step={1}
              type="number"
              value={scenario.pulses}
            />
            <span className="mt-1 block text-[11px] text-slate-500">Es el tamaño real del experimento; los shots se derivan del backend.</span>
          </label>
          <label className="block">
            <span className="flex items-center gap-1 text-xs font-medium text-slate-300">Semilla reproducible <InfoTip label="Semilla reproducible" text={fieldHelp('scenario.seed')} /></span>
            <input
              aria-label="Semilla reproducible"
              className="mt-1.5 h-10 w-full rounded-lg border border-border bg-surface px-3 font-mono text-sm text-white focus:border-cyan"
              min={0}
              onChange={(event) => updateField('scenario.seed', Number(event.target.value))}
              step={1}
              type="number"
              value={scenario.seed}
            />
            <span className="mt-1 block text-[11px] text-slate-500">Repite el muestreo con el mismo escenario y entorno.</span>
          </label>
          <label className="block">
            <span className="flex items-center gap-1 text-xs font-medium text-slate-300">Reloj de emisión <InfoTip label="Reloj de emisión" text={fieldHelp('scenario.clock_rate_hz')} /></span>
            <input
              aria-label="Reloj de emisión"
              className="mt-1.5 h-10 w-full rounded-lg border border-border bg-surface px-3 font-mono text-sm text-white focus:border-cyan"
              min={1}
              onChange={(event) => updateField('scenario.clock_rate_hz', Number(event.target.value))}
              step="any"
              type="number"
              value={scenario.clock_rate_hz}
            />
            <span className="mt-1 block text-[11px] text-slate-500">Frecuencia nominal en Hz usada para tasas y timing.</span>
          </label>
          <div className="rounded-lg border border-border bg-surface/70 p-3">
            <label className="flex cursor-pointer items-start gap-3">
              <input
                checked={scenario.store_full_event_log}
                className="mt-0.5 h-4 w-4 accent-cyan"
                onChange={(event) => updateField('scenario.store_full_event_log', event.target.checked)}
                type="checkbox"
              />
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-xs font-medium text-slate-200"><Database aria-hidden="true" className="text-cyan" size={14} /> Conservar todos los eventos <InfoTip label="Conservar todos los eventos" text={fieldHelp('scenario.store_full_event_log')} /></span>
                <span className="mt-1 block text-[11px] leading-4 text-slate-500">Guarda cada muestra para inspección y descarga. Límite del panel: 20.000 eventos.</span>
              </span>
            </label>
            {!scenario.store_full_event_log ? (
              <label className="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3 text-xs text-slate-400">
                <span className="flex items-center gap-1">Muestra representativa <InfoTip label="Muestra representativa" text={fieldHelp('scenario.event_sample_size')} /></span>
                <span className="flex items-center gap-2">
                  <input
                    aria-label="Tamaño de la muestra de eventos"
                    className="h-8 w-24 rounded-lg border border-border bg-background px-2 text-right font-mono text-white focus:border-cyan"
                    max={200}
                    min={0}
                    onChange={(event) => updateField('scenario.event_sample_size', Number(event.target.value))}
                    step={1}
                    type="number"
                    value={scenario.event_sample_size}
                  />
                  <span>eventos</span>
                </span>
              </label>
            ) : (
              <p className="mt-3 border-t border-warning/20 pt-3 text-[11px] text-warning">El coste de memoria crece con cada pulso.</p>
            )}
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
          <span>Semilla <b className="font-mono font-normal text-slate-300">{scenario.seed}</b></span>
          <span>Coste <b className="font-mono font-normal text-slate-300">{costEstimate ? `${costEstimate.total_pulse_events.toLocaleString('es-ES')} pulsos` : 'calculando'}</b></span>
          <span>Backend <b className="font-mono font-normal text-slate-300">{costEstimate?.backend ?? '—'}</b></span>
        </div>
        {apiOffline ? <p className="mt-3 text-sm text-warning" role="status">La API no está disponible: ejecutarás cuando vuelva la conexión.</p> : null}
        {validationBlocked ? <p className="mt-3 text-sm text-danger">Corrige los errores de validación antes de ejecutar.</p> : null}
        {blockedAttempt && validationBlocked ? (
          <p className="mt-3 rounded-lg border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger" role="alert">
            No se puede ejecutar todavía: corrige los campos marcados y vuelve a intentarlo.
          </p>
        ) : null}
        {confirming && costEstimate ? (
          <Dialog
            description={`${costEstimate.total_pulse_events.toLocaleString('es-ES')} pulsos y hasta ${costEstimate.estimated_max_shots.toLocaleString('es-ES')} shots. ${costEstimate.warnings.join(' ')}`}
            onClose={() => setConfirming(false)}
            open
            title="Confirmar ejecución"
          >
            <ConfirmPanel
              confirmLabel="Ejecutar con esta cota"
              description={`${costEstimate.total_pulse_events.toLocaleString('es-ES')} pulsos y hasta ${costEstimate.estimated_max_shots.toLocaleString('es-ES')} shots. ${costEstimate.warnings.join(' ')}`}
              onCancel={() => setConfirming(false)}
              onConfirm={() => { setConfirming(false); runMutation.mutate() }}
              pending={runMutation.isPending}
              title="Trabajo de coste elevado"
            />
          </Dialog>
        ) : null}
        {displayedStatus ? (
          <div aria-live="polite" className="mt-4 border-l-2 border-cyan/50 pl-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="font-mono text-slate-300">{displayedStatus.job_id}</span>
              <span className="text-slate-400">{statusLabel(displayedStatus.status)} · {displayedStatus.elapsed_s.toFixed(2)} s</span>
            </div>
            <div aria-label={`Progreso ${Math.round(progressPercent)} %`} className="mt-2 h-1.5 overflow-hidden bg-background" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progressPercent)}>
              <div className="h-full bg-cyan transition-[width]" style={{ width: `${progressPercent}%` }} />
            </div>
          </div>
        ) : null}
        {runMutation.error && !isAbortError(runMutation.error) ? <ApiErrorSummary error={runMutation.error} /> : null}
        {resumeError ? <ApiErrorSummary error={resumeError} /> : null}
        {hydrationError ? <ApiErrorSummary error={hydrationError} recoveryHint="El job puede haber caducado; guarda los resultados importantes en la biblioteca." /> : null}
        {cancelMutation.error ? <ApiErrorSummary error={cancelMutation.error} /> : null}
      </div>

      {latestRun ? (
        <div className="p-4 sm:p-5">
          {draftChanged ? (
            <div className="mb-4 flex gap-3 border-l-2 border-warning bg-warning/5 px-3 py-2 text-sm text-warning">
              <AlertTriangle aria-hidden="true" className="mt-0.5 shrink-0" size={16} />
              <p>Hay cambios sin ejecutar. El resultado mostrado pertenece al snapshot <span className="font-mono">{latestRun.digest.slice(0, 12)}</span>, no al draft actual.</p>
            </div>
          ) : null}
          <ResultDetails latestRun={latestRun} previousRun={previousRun} />
        </div>
      ) : (
        <div className="p-4 sm:p-5">
          <EmptyState description="Al ejecutar se guardarán escenario, digest, semilla, hora, coste y resultado como un snapshot inmutable." title="Todavía no hay runs en este experimento" />
        </div>
      )}
    </section>
  )
}

function ensureCurrentGeneration(expected: number, current: number): void {
  if (expected !== current) throw new DOMException('Stale run response', 'AbortError')
}

export function ResultDetails({ latestRun, previousRun }: { latestRun: RunSnapshot; previousRun: RunSnapshot | null }) {
  const [activeTab, setActiveTab] = useState<ResultTab>('summary')
  const summary = latestRun.status.result_summary ?? {}
  const previousSummary = previousRun?.status.result_summary ?? null
  const presentation = resultPresentation(summary)
  const tabs = visibleResultTabs(latestRun.result, summary)
  const selectedTab = tabs.includes(activeTab) ? activeTab : tabs[0]

  return (
    <div>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-base font-semibold text-white">{latestRun.label}</h3>
            <StatusBadge summary={summary} />
          </div>
          <p className="mt-1 font-mono text-xs text-slate-500">
            {latestRun.digest.slice(0, 16)} · seed {latestRun.seed} · {formatTimestamp(latestRun.completedAt)}
          </p>
        </div>
        <p className="text-xs text-slate-500">job <span className="font-mono text-slate-300">{latestRun.jobId}</span></p>
      </div>
      <ResultMetricGrid current={summary} previous={previousSummary} />
      <SignalFunnel summary={summary} />
      <ResultInterpretation presentation={presentation} result={latestRun.result} summary={summary} />
      <div className="mt-5 flex flex-wrap gap-1 border-b border-border" role="tablist">
        {tabs.map((tab) => (
          <button aria-selected={selectedTab === tab} className={`border-b-2 px-3 py-2 text-sm ${selectedTab === tab ? 'border-cyan text-cyan' : 'border-transparent text-slate-400 hover:text-white'}`} key={tab} onClick={() => setActiveTab(tab)} role="tab" type="button">
            {tabLabel(tab)}
          </button>
        ))}
      </div>
      <div className="mt-4" role="tabpanel">
        {renderResultTab(
          selectedTab,
          latestRun.result,
          summary,
          latestRun.label,
          latestRun.scenario.store_full_event_log,
        )}
      </div>
    </div>
  )
}

function ResultMetricGrid({ current, previous }: { current: JsonObject; previous: JsonObject | null }) {
  const metrics = metricRecord(current)
  const previousMetrics = previous ? metricRecord(previous) : {}
  const presentation = resultPresentation(current)
  const previousPresentation = previous ? resultPresentation(previous) : null
  const cards = [
    metricCard('Detecciones', metrics.detected, previousMetrics.detected),
    metricCard('Bits sifted', metrics.sifted, previousMetrics.sifted),
    metricCard('Errores', metrics.errors, previousMetrics.errors),
    {
      label: 'QBER',
      value: presentation.qberDefined ? `${formatNumber(presentation.qberValue)} (n=${presentation.sampleSize})` : `No definido (n=${presentation.sampleSize})`,
      delta: interpretableDelta(presentation.qberValue, previousPresentation?.qberValue ?? null),
    },
    metricCard('Ganancia', metrics.gain, previousMetrics.gain),
    metricCard('Tasa sifted', metrics.sifted_key_rate_bps, previousMetrics.sifted_key_rate_bps, 'bit/s'),
    {
      label: 'Tasa secreta estimada',
      value: estimatedRateLabel(presentation),
      delta: interpretableDelta(presentation.rateEstimateBps, previousPresentation?.rateEstimateBps ?? null),
    },
    metricCard('Pérdida', metrics.loss_db, previousMetrics.loss_db, 'dB'),
  ]
  if (presentation.assessment?.protocol === 'e91' || presentation.observedChshS !== null) {
    cards.push({
      label: 'CHSH observado',
      value: presentation.observedChshS === null ? 'No definido' : `${formatNumber(presentation.observedChshS)} (${presentation.chshSampleSize === null ? 'n no disponible' : `n=${presentation.chshSampleSize}`})`,
      delta: interpretableDelta(presentation.observedChshS, previousPresentation?.observedChshS ?? null),
    })
  }
  return (
    <div className="mt-4 grid grid-cols-2 border border-border bg-background/40 sm:grid-cols-4 xl:grid-cols-8">
      {cards.map((card) => (
        <article className="min-w-0 border-b border-r border-border p-3 last:border-r-0 sm:[&:nth-last-child(-n+4)]:border-b-0 xl:border-b-0" key={card.label}>
          <p className="flex items-center gap-1 text-[11px] text-slate-500">{card.label}<InfoTip label={card.label} text={resultMetricHelp(card.label)} /></p>
          <p className="mt-1 break-words font-mono text-sm tabular-nums text-white">{card.value}</p>
          {card.delta !== null ? <p className="mt-1 text-[11px] text-slate-500">Δ {formatNumber(card.delta)}</p> : null}
        </article>
      ))}
    </div>
  )
}

function SignalFunnel({ summary }: { summary: JsonObject }) {
  const metrics = metricRecord(summary)
  const stages = [
    { label: 'Pulsos', value: finiteNumber(metrics.pulses) },
    { label: 'Emitidos', value: finiteNumber(metrics.emitted) },
    { label: 'Transmitidos', value: finiteNumber(metrics.transmitted) },
    { label: 'Detectados', value: finiteNumber(metrics.detected) },
    { label: 'Sifted', value: finiteNumber(metrics.sifted) },
  ]
  const maximum = Math.max(0, ...stages.map((stage) => stage.value ?? 0))
  if (maximum === 0) return null
  return (
    <section aria-label="Recorrido de las señales" className="mt-4 rounded-xl border border-border bg-background/35 p-3">
      <p className="text-xs font-medium text-slate-400">Recorrido de la muestra</p>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {stages.map((stage, index) => {
          const ratio = stage.value === null ? 0 : stage.value / maximum
          return (
            <div className="min-w-0" key={stage.label}>
              <div className="flex h-12 items-end justify-center rounded-lg bg-surface/70 px-2 pt-2">
                <div
                  className={`min-h-1 w-full rounded-t ${index < 2 ? 'bg-violet-400/70' : index < 4 ? 'bg-cyan/75' : 'bg-emerald-400/75'}`}
                  style={{ height: `${Math.max(8, ratio * 100)}%` }}
                />
              </div>
              <p className="mt-2 truncate text-[11px] text-slate-500">{stage.label}</p>
              <p className="truncate font-mono text-xs text-white">{stage.value === null ? '—' : stage.value.toLocaleString('es-ES')}</p>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function ResultInterpretation({ presentation, result, summary }: { presentation: ResultPresentation; result: JsonObject; summary: JsonObject }) {
  const scopeText = presentation.securityScope === 'pedagogical_asymptotic_diagnostic'
    ? 'Estimación pedagógica y asintótica; no es un análisis finite-key ni una garantía de seguridad componible.'
    : presentation.securityScope
      ? `Alcance declarado: ${presentation.securityScope}.`
      : 'Resultado archivado sin alcance declarado; interprétalo sólo como diagnóstico.'
  const classical = isRecord(result.classical) ? result.classical : isRecord(summary.classical) ? summary.classical : {}
  const metrics = metricRecord(summary)
  const originalErrors = finiteNumber(metrics.errors)
  const corrected = finiteNumber(classical.blocks_corrected)
  const residual = finiteNumber(classical.residual_mismatches)
  const ambiguous = finiteNumber(classical.ambiguous_blocks)
  const failedVerification = presentation.status === 'verification-failed'
  return (
    <div className="mt-4 grid gap-3 lg:grid-cols-2">
      {failedVerification ? (
        <article className="border-l-2 border-danger bg-danger/5 p-3 text-sm lg:col-span-2">
          <p className="font-medium text-white">La clave se descartó durante la reconciliación automática</p>
          <p className="mt-1 leading-6 text-slate-300">
            El QBER estaba por debajo del umbral, así que el simulador intentó corregir la clave.
            {originalErrors !== null && corrected !== null && residual !== null && ambiguous !== null
              ? ` Había ${Math.trunc(originalErrors)} diferencias; se aplicó una corrección en ${Math.trunc(corrected)} bloques, pero quedaron ${Math.trunc(residual)} bits distintos en ${Math.trunc(ambiguous)} bloque${ambiguous === 1 ? '' : 's'} ambiguo${ambiguous === 1 ? '' : 's'}. Dos errores dentro de un mismo bloque pueden compensarse en la paridad y pasar inadvertidos durante esa corrección.`
              : ' La comprobación final todavía encontró bits distintos entre Alice y Bob.'}
            {' '}Como las claves no coincidían, no se entregó ninguna clave final.
          </p>
          {presentation.rateEstimateStatus === 'inconsistent_with_key_status' ? <p className="mt-2 text-xs text-warning">La tasa positiva es una estimación teórica asintótica calculada con el QBER; no es una clave que haya superado esta comprobación concreta.</p> : null}
        </article>
      ) : null}
      <article className="border-l-2 border-cyan/50 bg-background/40 p-3 text-sm">
        <p className="font-medium text-white">Lectura objetiva</p>
        <p className="mt-1 text-slate-300">{scopeText}</p>
        {presentation.rateEstimateStatus === 'inconsistent_with_key_status' ? <p className="mt-2 text-xs text-warning">La tasa numérica no concuerda con el estado de clave y se conserva sólo como diagnóstico.</p> : null}
      </article>
      <details className="group border-l-2 border-border bg-background/40 p-3 text-sm" open={presentation.reasons.length > 0}>
        <summary className="flex cursor-pointer list-none items-center justify-between font-medium text-white">
          ¿Por qué este estado?<ChevronDown aria-hidden="true" className="transition-transform group-open:rotate-180" size={15} />
        </summary>
        {presentation.reasons.length ? <DisclosureList label="Condiciones observadas" values={presentation.reasons} /> : <p className="mt-2 text-xs text-slate-400">El resultado no incluye razones estructuradas adicionales.</p>}
        {presentation.assumptions.length ? <DisclosureList label="Supuestos" values={presentation.assumptions} /> : null}
      </details>
      {presentation.observedChshS !== null ? (
        <article className="border-l-2 border-warning/60 bg-warning/5 p-3 text-sm lg:col-span-2">
          <p className="font-medium text-white">Conclusión CHSH observada</p>
          <p className="mt-1 text-slate-300">{chshConclusion(presentation.assessment?.observed_threshold_exceeded)}</p>
          <p className="mt-1 text-xs text-warning">Diagnóstico con fair sampling y sin prueba de significación estadística.</p>
        </article>
      ) : null}
    </div>
  )
}

function DisclosureList({ label, values }: { label: string; values: string[] }) {
  return <div className="mt-3"><p className="text-xs font-medium uppercase tracking-[0.08em] text-slate-500">{label}</p><ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-slate-300">{values.map((value) => <li key={value}>{value}</li>)}</ul></div>
}

function renderResultTab(
  tab: ResultTab,
  result: JsonObject,
  summary: JsonObject,
  runLabel: string,
  fullEventLog: boolean,
) {
  if (tab === 'events' && Array.isArray(result.event_sample)) {
    return <EventExplorer events={result.event_sample} fullEventLog={fullEventLog} runLabel={runLabel} />
  }
  if (tab === 'decoy') return <DecoyResultView value={result.decoy ?? summary.decoy ?? {}} />
  if (tab === 'bell') return <GenericStructuredResultView value={result.bell ?? result.correlations ?? summary.bell ?? {}} />
  if (tab === 'classical') return <ClassicalResultView summary={summary} value={result.classical ?? summary.classical ?? {}} />
  if (tab === 'provenance') return <ProvenanceResultView value={result.provenance ?? summary.provenance ?? { scenario_digest: summary.scenario_digest ?? null }} />
  return <SummaryDataView summary={summary} />
}

function EventExplorer({
  events,
  fullEventLog,
  runLabel,
}: {
  events: unknown[]
  fullEventLog: boolean
  runLabel: string
}) {
  const rows = events.filter(isRecord)
  const counts = events.reduce<{ [status: string]: number }>((accumulator, event) => {
    const status = isRecord(event) ? String(event.timing_status ?? 'ok') : 'unknown'
    accumulator[status] = (accumulator[status] ?? 0) + 1
    return accumulator
  }, {})
  const maxCount = Math.max(1, ...Object.values(counts))
  const columns = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 8)
  const fileName = `${safeFileName(runLabel)}-eventos`
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-white">{rows.length.toLocaleString('es-ES')} eventos conservados</p>
          <p className="mt-1 text-xs text-slate-500">
            {fullEventLog ? 'Este run guardó el registro completo.' : 'Este run guardó una muestra representativa.'}
          </p>
        </div>
        <div className="flex gap-2">
          <Button disabled={!rows.length} onClick={() => downloadCsv(rows, `${fileName}.csv`)} size="sm" tone="neutral" type="button">
            <Download aria-hidden="true" size={13} /> CSV
          </Button>
          <Button disabled={!rows.length} onClick={() => downloadJson(`${fileName}.json`, rows)} size="sm" tone="neutral" type="button">
            <Download aria-hidden="true" size={13} /> JSON
          </Button>
        </div>
      </div>
      <div className="space-y-2" aria-label="Histograma accesible de eventos">
        {Object.entries(counts).map(([status, count]) => (
          <div className="grid grid-cols-[120px_1fr_48px] items-center gap-3" key={status}>
            <span className="font-mono text-xs text-slate-400">{status}</span>
            <div className="h-2 overflow-hidden rounded-full bg-background"><div className="h-full rounded-full bg-cyan" style={{ width: `${(100 * count) / maxCount}%` }} /></div>
            <span className="text-right font-mono text-xs text-slate-400">{count}</span>
          </div>
        ))}
      </div>
      {rows.length ? (
        <details className="rounded-xl border border-border bg-background/40">
          <summary className="cursor-pointer px-3 py-2.5 text-sm text-slate-300">Explorar tabla de muestras</summary>
          <div className="max-h-80 overflow-auto border-t border-border">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="sticky top-0 bg-raised text-slate-400">
                <tr>{columns.map((column) => <th className="px-3 py-2 font-medium" key={column}>{column}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.slice(0, 100).map((row, index) => (
                  <tr key={`${String(row.index ?? index)}-${index}`}>
                    {columns.map((column) => <td className="max-w-48 truncate px-3 py-2 font-mono text-slate-300" key={column} title={String(row[column] ?? '')}>{String(row[column] ?? '—')}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {rows.length > 100 ? <p className="border-t border-border px-3 py-2 text-xs text-slate-500">Vista limitada a 100 filas; las descargas incluyen las {rows.length.toLocaleString('es-ES')}.</p> : null}
        </details>
      ) : null}
    </div>
  )
}

function metricCard(label: string, value: unknown, previous: unknown, unit = '') {
  const numeric = finiteNumber(value)
  const formatted = numeric === null ? 'No disponible' : `${formatNumber(numeric)}${unit ? ` ${unit}` : ''}`
  return { label, value: formatted, delta: interpretableDelta(numeric, finiteNumber(previous)) }
}

function resultMetricHelp(label: string): string {
  const help: Record<string, string> = {
    Detecciones: 'Clics registrados por Bob, tanto de señal como de ruido.',
    'Bits sifted': 'Bits conservados después de comparar bases compatibles.',
    Errores: 'Bits distintos entre Alice y Bob antes de la reconciliación.',
    QBER: 'Fracción de errores entre los bits cribados observados.',
    Ganancia: 'Fracción de pulsos enviados que acabaron en una detección.',
    'Tasa sifted': 'Bits cribados por segundo antes de corrección y privacidad.',
    'Tasa secreta estimada': 'Estimación asintótica pedagógica; no certifica una clave final verificada.',
    Pérdida: 'Pérdida óptica total estimada a lo largo del enlace.',
    'CHSH observado': 'Valor CHSH calculado con coincidencias observadas en E91.',
  }
  return help[label] ?? 'Métrica observada en el snapshot de esta ejecución.'
}

function interpretableDelta(current: number | null, previous: number | null): number | null {
  return current !== null && previous !== null ? current - previous : null
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function estimatedRateLabel(presentation: ResultPresentation): string {
  if (presentation.rateEstimateBps === null || presentation.rateEstimateStatus === 'unavailable') return 'No disponible'
  return `${formatNumber(presentation.rateEstimateBps)} bit/s${presentation.rateEstimateStatus === 'inconsistent_with_key_status' ? ' (inconsistente)' : ''}`
}

function chshConclusion(exceeded: boolean | null | undefined): string {
  if (exceeded === true) return 'La muestra supera el umbral CHSH de referencia dentro del modelo observado.'
  if (exceeded === false) return 'La muestra no supera el umbral CHSH de referencia dentro del modelo observado.'
  return 'No se tomó una decisión de umbral CHSH con esta muestra.'
}

function tabLabel(tab: ResultTab): string {
  const labels: { [key: string]: string } = { summary: 'Datos', decoy: 'Decoy', bell: 'Bell', events: 'Eventos', classical: 'Clásico', provenance: 'Procedencia' }
  return labels[tab] ?? tab
}

function statusLabel(status: JobStatus['status']): string {
  const labels: { [key in JobStatus['status']]: string } = {
    queued: 'En cola', running: 'En ejecución', cancellation_requested: 'Cancelación solicitada', cancelled: 'Cancelado', timed_out: 'Tiempo agotado', done: 'Completado', error: 'Error de ejecución', interrupted: 'Interrumpido al reiniciar', expired: 'Expirado',
  }
  return labels[status]
}

function formatTimestamp(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('es-ES', { dateStyle: 'short', timeStyle: 'medium' }).format(date)
}
