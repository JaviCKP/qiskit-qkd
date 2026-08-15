import { ArrowRight, RadioReceiver, Route, Send, SlidersHorizontal } from 'lucide-react'

import type { JsonObject, ScenarioPayload } from '@/api/client'
import type { MediumId } from './mediums'
import { formatNumber } from '@/lib/format'

export function LinkCockpit({
  effectiveScenario,
  channelState,
  sourceState,
  detectorState,
  timingState,
  mediumId = 'custom',
}: {
  effectiveScenario: ScenarioPayload
  channelState: JsonObject
  sourceState: JsonObject
  detectorState: JsonObject
  timingState: JsonObject
  mediumId?: MediumId
}) {
  const accent = mediumAccent(mediumId)
  const nodes = [
    { label: 'Emisor', model: effectiveScenario.source.kind, Icon: Send, color: 'text-violet-300' },
    { label: 'Canal', model: effectiveScenario.channel.kind, Icon: Route, color: accent },
    { label: 'Detector', model: effectiveScenario.detector.kind, Icon: RadioReceiver, color: 'text-emerald-300' },
    { label: 'Postprocesado', model: postProcessingLabel(effectiveScenario), Icon: SlidersHorizontal, color: 'text-amber-300' },
  ]
  const metrics = [
    { label: 'Pérdida total', value: withUnit(channelState.loss_db, 'dB') },
    { label: 'Transmitancia', value: formatNumber(channelState.transmittance) },
    { label: 'Eficiencia de Bob', value: formatPercent(effectiveScenario.detector.efficiency) },
    { label: 'Ruido por ventana', value: formatNumber(detectorState.p_dark_per_gate) },
    { label: 'Jitter efectivo', value: withUnit(timingState.effective_jitter_std_s, 's') },
    { label: 'Fotones / s', value: formatNumber(sourceState.mean_photon_rate_hz) },
  ]

  return (
    <section aria-label="Vista previa del enlace efectivo" className="overflow-hidden rounded-2xl border border-border bg-surface">
      <div className="grid gap-px bg-border lg:grid-cols-[1.15fr_1fr]">
        <div className="bg-gradient-to-r from-surface to-raised/60 p-4 sm:p-5">
          <div className="mb-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Vista previa calculada</p>
            <h2 className="mt-1 text-base font-semibold text-white">Así queda el enlace antes de ejecutarlo</h2>
          </div>
          <div className="grid items-center gap-2 sm:grid-cols-[repeat(7,minmax(0,1fr))]">
            {nodes.map(({ label, model, Icon, color }, index) => (
              <div className="contents" key={label}>
                {index > 0 ? <ArrowRight aria-hidden="true" className="hidden text-slate-600 sm:block" size={16} /> : null}
                <div className="flex min-w-0 items-center gap-3 rounded-xl border border-border bg-background/60 px-3 py-3">
                  <Icon aria-hidden="true" className={`shrink-0 ${color}`} size={17} />
                  <div className="min-w-0">
                    <p className="text-[11px] text-slate-500">{label}</p>
                    <p className="truncate text-xs font-medium text-slate-200" title={model}>{friendlyModel(model)}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3 lg:grid-cols-3">
          {metrics.map((metric) => (
            <div className="min-w-0 bg-background/70 p-3 sm:p-4" key={metric.label}>
              <dt className="text-xs text-slate-500">{metric.label}</dt>
              <dd className="mt-1 truncate font-mono text-sm tabular-nums text-white" title={metric.value}>{metric.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="border-t border-border bg-background/40 px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-slate-300">Tendencia esperada del enlace</p>
            <p className="mt-1 text-xs text-slate-500">La transmitancia cae cuando aumentan las pérdidas del medio.</p>
          </div>
          <svg aria-label={`Gráfica de tendencia para medio ${mediumId}`} className="h-12 w-full max-w-[240px]" role="img" viewBox="0 0 240 48">
            <path d="M2 10 C32 12 46 14 68 18 S112 24 132 28 S180 35 238 43" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="3" className={accent} />
            <path d="M2 10 C32 12 46 14 68 18 S112 24 132 28 S180 35 238 43 L238 48 L2 48 Z" fill="currentColor" className={`${accent} opacity-10`} />
          </svg>
        </div>
      </div>
    </section>
  )
}

function mediumAccent(mediumId: MediumId): string {
  return {
    ideal: 'text-emerald-300',
    fiber: 'text-sky-300',
    vacuum: 'text-violet-300',
    air: 'text-amber-300',
    satellite: 'text-indigo-300',
    underwater: 'text-cyan',
    custom: 'text-slate-300',
  }[mediumId]
}

function postProcessingLabel(scenario: ScenarioPayload): string {
  if (scenario.protocol.name === 'e91') return 'CHSH / clave'
  if (scenario.post_processing.decoy_security_estimation_enabled) return 'Sifting + decoy'
  return 'Sifting + reconciliación'
}

function friendlyModel(model: string): string {
  const labels: Record<string, string> = {
    decoy_weak_coherent: 'Coherente débil con decoys',
    weak_coherent: 'Coherente débil',
    ideal_single_photon: 'Fotón único ideal',
    entangled_pair: 'Par entrelazado',
    free_space: 'Espacio libre',
    underwater: 'Canal submarino',
    threshold: 'Detector umbral',
    ideal: 'Ideal',
    fiber: 'Fibra óptica',
    space: 'Vacío / espacio',
  }
  return labels[model] ?? model.replaceAll('_', ' ')
}

function withUnit(value: unknown, unit: string): string {
  const formatted = formatNumber(value)
  return formatted === '—' ? formatted : `${formatted} ${unit}`
}

function formatPercent(value: number): string {
  return `${formatNumber(value * 100)} %`
}
