import { CheckCircle2, CircleAlert, Cpu, Fingerprint, ShieldCheck, Waypoints } from 'lucide-react'

import type { JsonObject } from '@/api/client'
import { InfoTip } from '@/components/ui'
import { isRecord } from '@/features/shared/scenarioPaths'
import { formatNumber, metricRecord } from '@/lib/format'

type DisplayEntry = { label: string; value: unknown; help?: string; unit?: string }

const metricDisplay: Record<string, { label: string; help: string; unit?: string }> = {
  pulses: { label: 'Pulsos simulados', help: 'Número total de señales intentadas en la ejecución.' },
  emitted: { label: 'Pulsos emitidos', help: 'Pulsos que contenían al menos un fotón según el modelo de fuente.' },
  transmitted: { label: 'Pulsos transmitidos', help: 'Pulsos que sobrevivieron a la propagación por el canal.' },
  detected: { label: 'Detecciones', help: 'Clics registrados por Bob, incluidos señal y ruido.' },
  sifted: { label: 'Bits cribados', help: 'Bits conservados después de comparar las bases compatibles.' },
  errors: { label: 'Discrepancias', help: 'Bits distintos entre Alice y Bob antes de la reconciliación.' },
  qber: { label: 'QBER', help: 'Fracción de errores observada entre los bits cribados.' },
  loss_db: { label: 'Pérdida total', help: 'Pérdida óptica total estimada en el enlace.', unit: 'dB' },
  gain: { label: 'Ganancia', help: 'Fracción de pulsos enviados que terminaron en una detección.' },
  raw_detection_rate_hz: { label: 'Tasa de detección', help: 'Detecciones por segundo calculadas con el reloj de emisión.', unit: 'Hz' },
  sifted_key_rate_bps: { label: 'Tasa cribada', help: 'Bits cribados por segundo antes de corrección y privacidad.', unit: 'bit/s' },
  secret_key_rate_bps: { label: 'Tasa secreta estimada', help: 'Estimación pedagógica y asintótica; no equivale a una clave final verificada.', unit: 'bit/s' },
  abort: { label: 'Aborto por umbral', help: 'Indica si el QBER superó el umbral configurado.' },
  timing_discards: { label: 'Descartes temporales', help: 'Detecciones rechazadas por quedar fuera de la ranura temporal aceptada.' },
  dead_time_discards: { label: 'Descartes por tiempo muerto', help: 'Clics ignorados porque el detector aún se estaba recuperando.' },
  afterpulse_clicks: { label: 'Clics de afterpulse', help: 'Clics espurios producidos por memoria de una detección anterior.' },
  chsh_s: { label: 'CHSH observado', help: 'Valor CHSH calculado con las coincidencias observadas en E91.' },
  qber_margin: { label: 'Margen hasta el umbral QBER', help: 'Diferencia entre el umbral de aborto y el QBER observado.' },
  chsh_margin: { label: 'Margen CHSH', help: 'Diferencia entre el CHSH observado y el umbral de referencia.' },
}

export function SummaryDataView({ summary }: { summary: JsonObject }) {
  const metrics = metricRecord(summary)
  const entries = Object.entries(metrics)
    .filter(([key, value]) => isObservedKey(key) && key !== 'secure' && typeof value !== 'object')
    .map(([key, value]) => {
      const display = metricDisplay[key]
      return {
        label: display?.label ?? humanizeKey(key),
        help: display?.help ?? 'Valor diagnóstico almacenado por el simulador para esta ejecución.',
        unit: display?.unit,
        value,
      }
    })
  return entries.length ? <ResultCardGrid entries={entries} /> : <UnavailableMessage text="Este run no incluye métricas agregadas para mostrar." />
}

export function ClassicalResultView({ value, summary }: { value: unknown; summary: JsonObject }) {
  const classical = isRecord(value) ? value : {}
  const metrics = metricRecord(summary)
  const originalErrors = count(metrics.errors)
  const corrected = count(classical.blocks_corrected)
  const ambiguous = count(classical.ambiguous_blocks)
  const residual = count(classical.residual_mismatches)
  const finalLength = count(classical.final_key_length)
  const threshold = numberValue(classical.threshold ?? classical.qber_abort_threshold)
  const observedQber = numberValue(classical.estimated_qber ?? metrics.qber)
  const verificationPassed = classical.verification_passed === true
  const verificationFailed = classical.verification_passed === false || classical.verification_status === 'failed'
  return (
    <div className="space-y-4">
      <div className={`rounded-panel border p-4 ${verificationFailed ? 'border-danger/40 bg-danger/5' : 'border-success/30 bg-success/5'}`}>
        <div className="flex gap-3">
          {verificationFailed ? <CircleAlert aria-hidden="true" className="mt-0.5 shrink-0 text-danger" size={20} /> : <CheckCircle2 aria-hidden="true" className="mt-0.5 shrink-0 text-success" size={20} />}
          <div>
            <h4 className="text-sm font-semibold text-white">Reconciliación de Alice y Bob</h4>
            <p className="mt-1 text-sm leading-6 text-slate-300">
              {verificationFailed
                ? `La comprobación final encontró ${residual} discrepancia${residual === 1 ? '' : 's'} residual${residual === 1 ? '' : 'es'}; Alice y Bob no compartían la misma clave y el simulador la descartó.`
                : verificationPassed
                  ? 'La comprobación final confirmó que Alice y Bob terminaron con la misma clave corregida.'
                  : 'Este resultado no incluye una decisión explícita de verificación final.'}
            </p>
          </div>
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <StageCard label="1 · Error observado" value={observedQber === null ? 'No disponible' : `${formatNumber(observedQber * 100)} %`} detail={`${originalErrors ?? '—'} diferencias iniciales`} />
        <StageCard label="2 · Umbral" value={threshold === null ? 'No configurado' : `${formatNumber(threshold * 100)} %`} detail={classical.threshold_exceeded === true ? 'Umbral superado' : 'QBER bajo el umbral'} />
        <StageCard label="3 · Corrección" value={`${corrected ?? 0} bloques`} detail={`${ambiguous ?? 0} bloque${ambiguous === 1 ? '' : 's'} ambiguo${ambiguous === 1 ? '' : 's'}`} />
        <StageCard label="4 · Verificación" value={`${residual ?? 0} discrepancias residuales`} detail={`${finalLength ?? 0} bits de clave final`} />
      </div>
      <ResultCardGrid entries={[
        { label: 'Bits cribados', value: classical.sifted_key_length ?? metrics.sifted, help: 'Bits disponibles antes de revelar información para reconciliar.' },
        { label: 'Bits candidatos', value: classical.candidate_key_length, help: 'Bits que entraron en la corrección de errores.' },
        { label: 'Información revelada', value: classical.leak_ec ?? classical.leak_ec_bits, help: 'Bits de información expuestos durante la corrección.', unit: 'bits' },
        { label: 'Tamaño de bloque', value: classical.reconciliation_block_size, help: 'Bits agrupados por cada comprobación de paridad.' },
      ].filter((entry) => entry.value !== undefined)} />
    </div>
  )
}

export function DecoyResultView({ value }: { value: unknown }) {
  const raw = isRecord(value) ? value : {}
  const root = isRecord(raw.decoy) && !isRecord(raw.signal) && (isRecord(raw.decoy.signal) || isRecord(raw.decoy.security)) ? raw.decoy : raw
  const security = isRecord(root.security) ? root.security : {}
  const intensities = Object.entries(root)
    .filter(([name, item]) => name !== 'security' && isRecord(item) && ('mean_photon_number' in item || 'pulses' in item))
    .map(([name, item]) => ({ name, item: item as JsonObject }))
  return (
    <div className="space-y-4">
      {Object.keys(security).length ? (
        <div className="rounded-panel border border-violet/25 bg-violet/[0.06] p-4">
          <div className="flex items-start gap-3">
            <ShieldCheck aria-hidden="true" className="mt-0.5 shrink-0 text-violet" size={20} />
            <div>
              <h4 className="text-sm font-semibold text-white">Estimación con estados decoy</h4>
              <p className="mt-1 text-sm text-slate-300">Compara intensidades distintas para acotar la contribución de pulsos de un solo fotón.</p>
            </div>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <MiniValue label="Método" value={security.method} />
            <MiniValue label="Tasa decoy estimada" value={formatWithUnit(security.secret_key_rate_bps, 'bit/s')} />
            <MiniValue label="Rendimiento de 1 fotón ≥" value={formatPercent(security.single_photon_yield_lower_bound)} />
            <MiniValue label="Error de 1 fotón ≤" value={formatPercent(security.single_photon_error_rate_upper_bound)} />
          </div>
        </div>
      ) : null}
      {intensities.length ? (
        <div className="overflow-x-auto rounded-panel border border-border">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="bg-raised text-slate-400"><tr><th className="px-3 py-2.5">Intensidad</th><th className="px-3 py-2.5">μ</th><th className="px-3 py-2.5">Selección</th><th className="px-3 py-2.5">Pulsos</th><th className="px-3 py-2.5">Emitidos</th><th className="px-3 py-2.5">Detectados</th><th className="px-3 py-2.5">Cribados</th><th className="px-3 py-2.5">Ganancia</th><th className="px-3 py-2.5">QBER</th></tr></thead>
            <tbody className="divide-y divide-border bg-background/35">
              {intensities.map(({ name, item }) => <tr key={name}><td className="px-3 py-2.5 font-medium text-white">{intensityLabel(name)}</td><ValueCell value={item.mean_photon_number} /><ValueCell value={formatPercent(item.selection_fraction ?? item.selection_probability)} /><ValueCell value={item.pulses} /><ValueCell value={item.emitted} /><ValueCell value={item.detected} /><ValueCell value={item.sifted} /><ValueCell value={item.gain} /><ValueCell value={formatPercent(item.qber)} /></tr>)}
            </tbody>
          </table>
        </div>
      ) : <p className="text-sm text-slate-400">No hay desglose de intensidades decoy en este resultado.</p>}
    </div>
  )
}

export function ProvenanceResultView({ value }: { value: unknown }) {
  const provenance = isRecord(value) ? value : {}
  const effective = isRecord(provenance.effective_model) ? provenance.effective_model : {}
  const consumed = Array.isArray(effective.consumed_parameters) ? effective.consumed_parameters : []
  const ignored = Array.isArray(effective.ignored_parameters) ? effective.ignored_parameters : []
  if (!Object.values(provenance).some((item) => item !== null && item !== undefined)) {
    return <UnavailableMessage text="Este run no incluye información de procedencia." />
  }
  return (
    <div className="space-y-4">
      {provenance.verification_status === 'unverified_import' ? (
        <p className="rounded-panel border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning" role="status">
          Procedencia importada sin verificar. Los valores se conservan como afirmaciones del archivo y no como evidencia del runtime local.
        </p>
      ) : null}
      <div className="grid gap-3 md:grid-cols-3">
        <ProvenanceCard Icon={Cpu} title="Motor de simulación" rows={[
          ['Backend', provenance.backend], ['Primitiva', provenance.primitive], ['Qiskit', provenance.qiskit_version], ['Qiskit Aer', provenance.qiskit_aer_version],
        ]} />
        <ProvenanceCard Icon={Waypoints} title="Modelos efectivos" rows={[
          ['Protocolo', provenance.protocol ?? effective.protocol_model], ['Fuente', provenance.source_model ?? effective.source_model], ['Canal', provenance.channel_model ?? effective.channel_model], ['Detector', provenance.detector_model ?? effective.detector_model],
        ]} />
        <ProvenanceCard Icon={Fingerprint} title="Reproducibilidad" rows={[
          ['Semilla', provenance.seed ?? provenance.effective_scenario_seed], ['Semilla backend', provenance.backend_seed], ['Shots por circuito', provenance.shots_per_circuit], ['Digest', provenance.effective_scenario_digest ?? provenance.scenario_digest],
        ]} />
      </div>
      {consumed.length || ignored.length ? (
        <details className="rounded-panel border border-border bg-background/35">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-slate-300">Parámetros aplicados por el motor</summary>
          <div className="grid gap-4 border-t border-border p-4 md:grid-cols-2">
            <ParameterList label={`Aplicados (${consumed.length})`} values={consumed} tone="text-success" />
            <ParameterList label={`Ignorados por este modelo (${ignored.length})`} values={ignored} tone="text-slate-500" />
          </div>
        </details>
      ) : null}
    </div>
  )
}

export function GenericStructuredResultView({ value }: { value: unknown }) {
  if (!isRecord(value)) return <p className="text-sm text-slate-400">No hay datos estructurados para esta sección.</p>
  const entries = flattenEntries(value)
  return <ResultCardGrid entries={entries.map(([key, item]) => ({ label: humanizeKey(key), value: item, help: 'Valor observado almacenado por el simulador.' }))} />
}

function ResultCardGrid({ entries }: { entries: DisplayEntry[] }) {
  return <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{entries.map((entry) => <div className="min-w-0 rounded-panel border border-border bg-background/40 p-3" key={entry.label}><dt className="flex items-center gap-1 text-xs text-slate-500">{entry.label}{entry.help ? <InfoTip label={entry.label} text={entry.help} /> : null}</dt><dd className="mt-1 break-words font-mono text-sm text-slate-100">{formatDisplayValue(entry.value, entry.unit)}</dd></div>)}</dl>
}

function StageCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="rounded-panel border border-border bg-background/40 p-3"><p className="text-2xs font-medium uppercase tracking-[0.06em] text-slate-500">{label}</p><p className="mt-1 font-mono text-sm text-white">{value}</p><p className="mt-1 text-xs text-slate-400">{detail}</p></article>
}

function MiniValue({ label, value }: { label: string; value: unknown }) {
  return <div className="rounded-control bg-background/45 p-2.5"><p className="text-2xs text-slate-500">{label}</p><p className="mt-1 break-words font-mono text-xs text-white">{formatDisplayValue(value)}</p></div>
}

function ProvenanceCard({ Icon, title, rows }: { Icon: typeof Cpu; title: string; rows: Array<[string, unknown]> }) {
  return <article className="rounded-panel border border-border bg-background/40 p-4"><div className="flex items-center gap-2"><Icon aria-hidden="true" className="text-cyan" size={17} /><h4 className="text-sm font-medium text-white">{title}</h4></div><dl className="mt-3 space-y-2">{rows.filter(([, value]) => value !== undefined && value !== null).map(([label, value]) => <div className="flex min-w-0 items-start justify-between gap-3 text-xs" key={label}><dt className="shrink-0 text-slate-500">{label}</dt><dd className="min-w-0 break-all text-right font-mono text-slate-200">{formatDisplayValue(value)}</dd></div>)}</dl></article>
}

function ParameterList({ label, values, tone }: { label: string; values: unknown[]; tone: string }) {
  return <div><p className={`text-xs font-medium ${tone}`}>{label}</p><ul className="mt-2 grid gap-1 text-2xs text-slate-400 sm:grid-cols-2">{values.map((value, index) => <li className="truncate font-mono" key={`${String(value)}-${index}`} title={String(value)}>• {String(value)}</li>)}</ul></div>
}

function ValueCell({ value }: { value: unknown }) {
  return <td className="px-3 py-2.5 font-mono text-slate-300">{formatDisplayValue(value)}</td>
}

function flattenEntries(value: JsonObject, prefix = ''): Array<[string, unknown]> {
  return Object.entries(value).filter(([key]) => isObservedKey(key)).flatMap(([key, item]) => isRecord(item)
    ? flattenEntries(item, prefix ? `${prefix} · ${humanizeKey(key)}` : humanizeKey(key))
    : [[prefix ? `${prefix} · ${humanizeKey(key)}` : humanizeKey(key), item] as [string, unknown]])
}

/**
 * Result sections are Alice/Bob-facing observations.  Eve traces are
 * available only from the explicit diagnostics API channel and must not be
 * rendered as if they were protocol evidence if a legacy/imported payload
 * still contains them.
 */
function isObservedKey(key: string): boolean {
  return key !== 'eavesdropper' && key !== 'tags' && !key.startsWith('eve_')
}

function formatDisplayValue(value: unknown, unit?: string): string {
  if (value === null || value === undefined) return 'No disponible'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (typeof value === 'number') return `${formatNumber(value)}${unit ? ` ${unit}` : ''}`
  if (Array.isArray(value)) return value.length ? value.map(String).join(', ') : 'Ninguno'
  if (isRecord(value)) return `${Object.keys(value).length} valores`
  return String(value)
}

function formatPercent(value: unknown): string {
  const number = numberValue(value)
  return number === null ? 'No disponible' : `${formatNumber(number * 100)} %`
}

function formatWithUnit(value: unknown, unit: string): string {
  const number = numberValue(value)
  return number === null ? 'No disponible' : `${formatNumber(number)} ${unit}`
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function count(value: unknown): number | null {
  const number = numberValue(value)
  return number === null ? null : Math.max(0, Math.trunc(number))
}

function humanizeKey(key: string): string {
  return key.replaceAll('_', ' ').replace(/^./, (letter) => letter.toUpperCase())
}

function intensityLabel(name: string): string {
  return ({ signal: 'Señal', decoy: 'Decoy débil', vacuum: 'Vacío' } as Record<string, string>)[name] ?? humanizeKey(name)
}

function UnavailableMessage({ text }: { text: string }) {
  return <p className="rounded-panel border border-dashed border-border bg-background/30 px-4 py-6 text-center text-sm text-slate-500">{text}</p>
}
