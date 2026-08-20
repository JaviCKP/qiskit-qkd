import { ArrowRight, RadioReceiver, Route, Send, SlidersHorizontal } from 'lucide-react'

import type { JsonObject, ScenarioPayload } from '@/api/client'
import { Meter, StackedBar, StackedBarRows, StatTile } from '@/components/dataviz'
import { InfoTip } from '@/components/ui'
import { formatNumber, percent } from '@/lib/format'

import { decoyPhotonRows, lossBudget, numberOr } from './linkBudget'

import type { MediumId } from './mediums'

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
    { label: 'Emisor', model: effectiveScenario.source.kind, Icon: Send, color: 'text-violet' },
    { label: 'Canal', model: effectiveScenario.channel.kind, Icon: Route, color: accent },
    { label: 'Detector', model: effectiveScenario.detector.kind, Icon: RadioReceiver, color: 'text-success' },
    { label: 'Postprocesado', model: postProcessingLabel(effectiveScenario), Icon: SlidersHorizontal, color: 'text-warning' },
  ]
  const lossTotal = numberOr(channelState.loss_db, null)
  const budget = lossBudget(channelState)
  const transmittance = numberOr(channelState.transmittance, null)
  const efficiency = numberOr(effectiveScenario.detector.efficiency, 0)
  const inGate = numberOr(timingState.in_gate_probability, null)
  const geometric = numberOr(channelState.geometric_transmittance, null)
  const photonRows = decoyPhotonRows(sourceState)

  const stats = [
    {
      label: 'Pérdida total del canal',
      value: lossTotal === null ? '—' : formatNumber(lossTotal),
      unit: 'dB',
      tone: lossTone(lossTotal),
      footnote: transmittance === null ? undefined : `Transmitancia ${formatNumber(transmittance)}`,
    },
    {
      label: 'Fotones por segundo',
      value: formatNumber(sourceState.mean_photon_rate_hz),
      unit: 'Hz',
      tone: 'neutral' as const,
      footnote: sourceRateFootnote(effectiveScenario, sourceState),
    },
    {
      label: 'Ruido por ventana',
      value: formatNumber(detectorState.p_dark_per_gate),
      tone: 'neutral' as const,
      footnote: `Ventana ${formatNumber(detectorState.gate_width_s)} s`,
    },
    {
      label: 'Jitter efectivo',
      value: formatNumber(timingState.effective_jitter_std_s),
      unit: 's',
      tone: 'neutral' as const,
      footnote: inGate === null ? undefined : `${percent(inGate)} dentro de ventana`,
    },
  ]

  return (
    <section
      aria-label="Vista previa del enlace efectivo"
      className="overflow-hidden rounded-panel border border-border bg-surface bg-panel-sheen shadow-panel"
    >
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
        <div>
          <p className="text-2xs font-semibold uppercase tracking-eyebrow text-slate-500">Vista previa calculada</p>
          <h2 className="mt-1 text-base font-semibold text-white">Así queda el enlace antes de ejecutarlo</h2>
        </div>
        <p className="text-2xs text-slate-500">
          Valores obtenidos de la caracterización de la librería, sin ejecutar el protocolo.
        </p>
      </header>

      {/* Signal path -------------------------------------------------------- */}
      <div className="grid items-center gap-2 px-4 py-4 sm:grid-cols-[repeat(7,minmax(0,1fr))] sm:px-5">
        {nodes.map(({ label, model, Icon, color }, index) => (
          <div className="contents" key={label}>
            {index > 0 ? (
              <ArrowRight aria-hidden="true" className="mx-auto hidden text-slate-600 sm:block" size={16} />
            ) : null}
            <div className="flex min-w-0 items-center gap-3 rounded-control border border-border bg-background/60 px-3 py-2.5 transition-colors hover:border-border-strong">
              <Icon aria-hidden="true" className={`shrink-0 ${color}`} size={17} />
              <div className="min-w-0">
                <p className="text-2xs text-slate-500">{label}</p>
                <p className="truncate text-2xs font-medium text-slate-200" title={model}>{friendlyModel(model)}</p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Headline metrics --------------------------------------------------- */}
      <div className="grid gap-2 border-t border-border px-4 py-4 sm:grid-cols-2 sm:px-5 xl:grid-cols-4">
        {stats.map((stat) => (
          <StatTile
            footnote={stat.footnote}
            key={stat.label}
            label={stat.label}
            tone={stat.tone}
            unit={stat.unit}
            value={stat.value}
          />
        ))}
      </div>

      {/* Charts driven by the characterisation payload ----------------------- */}
      <div className="grid gap-px border-t border-border bg-border lg:grid-cols-2">
        <div className="bg-surface p-4 sm:p-5">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-medium text-white">Presupuesto de pérdidas</h3>
              <p className="mt-0.5 text-2xs text-slate-500">
                {lossTotal === null
                  ? 'Sin caracterización disponible.'
                  : `Reparto de los ${formatNumber(lossTotal)} dB que atenúan el canal.`}
              </p>
            </div>
            <InfoTip
              label="Presupuesto de pérdidas"
              text="Descomposición en decibelios de la pérdida total del canal. Los términos conocidos se restan del total que devuelve la caracterización y el resto se agrupa como atenuación del medio, de modo que las partes siempre suman la pérdida real."
            />
          </div>
          <div className="mt-4">
            <StackedBar
              emptyLabel="Canal sin pérdidas: todos los términos valen 0 dB."
              formatValue={(value) => formatNumber(value)}
              segments={budget}
              total={lossTotal ?? undefined}
              unit="dB"
            />
          </div>
        </div>

        <div className="bg-surface p-4 sm:p-5">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-medium text-white">
                {photonRows ? 'Estadística de fotones por pulso' : 'Cadena de transmisión'}
              </h3>
              <p className="mt-0.5 text-2xs text-slate-500">
                {photonRows
                  ? 'Probabilidad de 0, 1 o varios fotones en cada intensidad.'
                  : 'Factores que recortan la señal entre lo emitido y lo detectado.'}
              </p>
            </div>
            <InfoTip
              label={photonRows ? 'Estadística de fotones' : 'Cadena de transmisión'}
              text={photonRows
                ? 'Los pulsos con más de un fotón son los que abren la puerta al ataque de división del número de fotones (PNS); las intensidades decoy sirven precisamente para acotar su contribución.'
                : 'Cada factor recorta la fracción de señal que sobrevive: geometría del haz, transmitancia total del canal, eficiencia del detector y probabilidad de caer dentro de la ventana temporal.'}
            />
          </div>
          <div className="mt-4">
            {photonRows ? (
              <StackedBarRows
                legend={[
                  { label: 'Vacío (0 fotones)', slot: 5 },
                  { label: '1 fotón', slot: 0 },
                  { label: '≥2 fotones', slot: 1 },
                ]}
                rows={photonRows}
              />
            ) : (
              <div className="space-y-3">
                {geometric !== null && geometric < 1 ? (
                  <Meter label="Transmitancia geométrica" max={1} tone="accent" value={geometric} />
                ) : null}
                <Meter
                  hint={lossTotal === null ? undefined : `Equivale a ${formatNumber(lossTotal)} dB de pérdida`}
                  label="Transmitancia del canal"
                  max={1}
                  tone="accent"
                  value={transmittance ?? 0}
                />
                <Meter label="Eficiencia del detector" max={1} tone="success" value={efficiency} />
                {inGate !== null ? (
                  <Meter
                    label="Dentro de la ventana temporal"
                    max={1}
                    tone={inGate < 0.9 ? 'warning' : 'success'}
                    value={inGate}
                  />
                ) : null}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

function sourceRateFootnote(scenario: ScenarioPayload, sourceState: JsonObject): string {
  const pairRate = numberOr(sourceState.pair_rate_hz, null)
  if (pairRate !== null) return `Pares ${formatNumber(pairRate)} Hz`
  return `Reloj ${formatNumber(scenario.clock_rate_hz)} Hz`
}

function lossTone(lossDb: number | null): 'neutral' | 'success' | 'warning' | 'danger' {
  if (lossDb === null) return 'neutral'
  if (lossDb >= 30) return 'danger'
  if (lossDb >= 15) return 'warning'
  return 'success'
}

function mediumAccent(mediumId: MediumId): string {
  return {
    ideal: 'text-success',
    fiber: 'text-cyan',
    vacuum: 'text-violet',
    air: 'text-warning',
    satellite: 'text-violet',
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
    satellite: 'Enlace satelital',
    underwater: 'Canal submarino',
    threshold: 'Detector umbral',
    ideal: 'Ideal',
    fiber: 'Fibra óptica',
    space: 'Vacío / espacio',
    deep_space: 'Espacio profundo',
    vacuum: 'Vacío',
    atmospheric: 'Atmosférico',
    water: 'Agua',
    marine: 'Marino',
  }
  return labels[model] ?? model.replaceAll('_', ' ')
}
