import { useMemo, useState } from 'react'
import { ChevronDown, Search } from 'lucide-react'

import type { ApiValidationIssue, CatalogField, CatalogSection, ScenarioPayload } from '@/api/client'
import { TemporalPatternBuilder } from '@/features/dynamics/TemporalPatternBuilder'
import type { MediumId } from '@/features/lab/mediums'
import { readTarget } from '@/features/shared/scenarioPaths'
import { formatInputValue } from '@/lib/format'

import { FieldControl } from './fieldControls'
import { visibleFieldsForMedium } from './fieldVisibility'

type InspectorMode = 'basic' | 'advanced'

const basicFields = new Set([
  'scenario.pulses',
  'scenario.clock_rate_hz',
  'scenario.seed',
  'protocol.name',
  'source.kind',
  'source.mean_photon_number',
  'source.preparation_error_probability',
  'source.decoy_intensities',
  'channel.kind',
  'channel.distance_km',
  'channel.attenuation_db_km',
  'channel.fixed_loss_db',
  'channel.depolarizing_probability',
  'channel.background_count_rate_hz',
  'detector.kind',
  'detector.efficiency',
  'detector.dark_count_rate_hz',
  'detector.gate_width_s',
  'timing.jitter_std_s',
  'post_processing.qber_abort_threshold',
  'post_processing.error_correction_efficiency',
  'eavesdropper.kind',
  'eavesdropper.intercept_probability',
  'e91.bell_state',
  'e91.chsh_estimation_enabled',
])

const sectionOrder = [
  'scenario',
  'source',
  'protocol',
  'channel',
  'detector',
  'timing',
  'eavesdropper',
  'e91',
  'post_processing',
]

export function FocusedInspector({
  errors,
  sections,
  scenario,
  mediumId,
  editedFields,
  onChange,
}: {
  errors: ApiValidationIssue[]
  sections: CatalogSection[]
  scenario: ScenarioPayload
  mediumId: MediumId
  editedFields: string[]
  onChange: (target: string, value: unknown) => void
}) {
  const [search, setSearch] = useState('')
  const [mode, setMode] = useState<InspectorMode>('basic')
  const visibleSections = useMemo(() => {
    const ordered = [...sections].sort(
      (a, b) => sectionOrder.indexOf(a.key) - sectionOrder.indexOf(b.key),
    )
    return ordered
      .filter((section) => section.key !== 'dynamic')
      .map((section) => ({
        section,
        fields: visibleFieldsForMedium({
          fields: section.fields,
          mediumId,
          scenario,
          expert: mode === 'advanced',
          search,
        }).filter((field) => mode === 'advanced' || search.trim() || basicFields.has(field.key)),
      }))
      .filter(({ fields }) => fields.length > 0)
  }, [mediumId, mode, scenario, search, sections])
  const visibleCount = visibleSections.reduce((total, item) => total + item.fields.length, 0)

  return (
    <section className="min-w-0 overflow-hidden rounded-panel border border-border bg-surface">
      <div className="border-b border-border px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-slate-500">
              Configuración técnica
            </p>
            <h2 className="mt-1 text-base font-semibold text-white">Recorrido físico del experimento</h2>
            <p className="mt-1 text-sm text-slate-400">
              Fuente → protocolo → canal → detector → timing → ruido → postprocesado
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div aria-label="Nivel de configuración" className="flex rounded-control border border-border bg-background p-0.5" role="group">
              {(['basic', 'advanced'] as const).map((value) => (
                <button
                  aria-pressed={mode === value}
                  className={`h-8 rounded-[3px] px-3 text-xs font-medium ${mode === value ? 'bg-raised text-cyan' : 'text-slate-400 hover:text-white'}`}
                  key={value}
                  onClick={() => setMode(value)}
                  type="button"
                >
                  {value === 'basic' ? 'Básico' : 'Avanzado'}
                </button>
              ))}
            </div>
            <label className="relative block min-w-0 sm:w-56">
              <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={15} />
              <span className="sr-only">Buscar parámetro</span>
              <input
                className="h-9 w-full rounded-control border border-border bg-background pl-9 pr-3 text-sm text-white focus:border-cyan"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Buscar parámetro"
                value={search}
              />
            </label>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {visibleCount} parámetros efectivos · {mode === 'basic' ? 'alto impacto' : 'modelo completo'}
        </p>
      </div>
      <div className="divide-y divide-border">
        {visibleSections.length === 0 ? (
          <p className="p-5 text-sm text-slate-400">No hay parámetros que coincidan con la búsqueda.</p>
        ) : null}
        {visibleSections.map(({ section, fields }, sectionIndex) => (
          <details className="group" key={section.key} open={mode === 'basic' || sectionIndex < 3}>
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 hover:bg-white/[0.025] sm:px-5">
              <div>
                <h3 className="text-sm font-semibold text-white">{section.label_es}</h3>
                <p className="mt-0.5 text-xs text-slate-500">{sectionDescription(section.key)}</p>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span>{fields.length}</span>
                <ChevronDown aria-hidden="true" className="transition-transform group-open:rotate-180" size={15} />
              </div>
            </summary>
            <div className="grid grid-cols-1 gap-px border-t border-border bg-border lg:grid-cols-2">
              {fields.map((field) => (
                <InspectorField
                  edited={editedFields.includes(field.key)}
                  error={fieldError(errors, field.key)}
                  field={field}
                  key={field.key}
                  mode={mode}
                  onChange={onChange}
                  value={readTarget(scenario, field.key) ?? field.default}
                />
              ))}
              {fields.length % 2 === 1 ? <div aria-hidden="true" className="hidden bg-surface lg:block" /> : null}
            </div>
          </details>
        ))}
        {mode === 'advanced' ? (
          <div className="p-4 sm:p-5">
            <TemporalPatternBuilder onChange={onChange} scenario={scenario} />
          </div>
        ) : null}
      </div>
    </section>
  )
}

function InspectorField({
  error,
  edited,
  field,
  value,
  mode,
  onChange,
}: {
  error: string | null
  edited: boolean
  field: CatalogField
  value: unknown
  mode: InspectorMode
  onChange: (target: string, value: unknown) => void
}) {
  const controlId = `field-${field.key.replaceAll('.', '-')}`
  const wide = ['json', 'table', 'schedule_list'].includes(field.type)
  const disabled = field.effect_status === 'ignored' || field.effect_status === 'unsupported'
  return (
    <div className={`min-w-0 bg-surface p-4 ${wide ? 'lg:col-span-2' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <label className="text-sm font-medium text-slate-200" htmlFor={controlId}>
            {field.label_es}{symbolFor(field.key) ? <span className="ml-1 font-mono text-xs text-cyan">{symbolFor(field.key)}</span> : null}
          </label>
          <p className="mt-1 text-xs leading-5 text-slate-500">{descriptionFor(field)}</p>
        </div>
        <span className={`shrink-0 rounded-control border px-1.5 py-0.5 text-[10px] uppercase tracking-[0.08em] ${edited ? 'border-cyan/40 text-cyan' : 'border-border text-slate-500'}`}>
          {edited ? 'usuario' : 'preset'}
        </span>
      </div>
      <div className="mt-3 flex min-w-0 items-start gap-2">
        <FieldControl disabled={disabled} field={field} id={controlId} onChange={onChange} value={value} />
        {field.unit ? <span className="mt-2.5 w-16 shrink-0 text-xs text-slate-500">{field.unit}</span> : null}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-600">
        <span>Rango {rangeLabel(field)}</span>
        <span>Por defecto {formatInputValue(field.default) || '—'}</span>
        {mode === 'advanced' ? <code className="break-all">{field.key}</code> : null}
      </div>
      <p className="mt-2 text-xs text-slate-400"><span className="text-slate-600">Efecto:</span> {effectFor(field)}</p>
      {disabled ? <p className="mt-2 text-xs text-warning">{field.effect_reason ?? 'Este valor no tiene efecto en la configuración actual.'}</p> : null}
      {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
    </div>
  )
}

function fieldError(errors: ApiValidationIssue[], fieldKey: string): string | null {
  return errors.find((error) => error.loc === fieldKey)?.msg ?? null
}

function sectionDescription(key: string): string {
  const descriptions: { [key: string]: string } = {
    scenario: 'Escala, reloj, semilla y registro.',
    source: 'Estado emitido y estadística de fotones.',
    protocol: 'Preparación y bases del protocolo.',
    channel: 'Propagación, pérdidas y perturbaciones.',
    detector: 'Eficiencia, ruido y recuperación.',
    timing: 'Ventanas, sincronización y jitter.',
    eavesdropper: 'Modelo explícito de Eve.',
    e91: 'Entrelazamiento y test CHSH.',
    post_processing: 'Sifting, estimación y reconciliación.',
  }
  return descriptions[key] ?? 'Parámetros del modelo.'
}

function descriptionFor(field: CatalogField): string {
  const descriptions: { [key: string]: string } = {
    'scenario.pulses': 'Número de señales cuánticas simuladas.',
    'scenario.clock_rate_hz': 'Frecuencia nominal de emisión de pulsos.',
    'scenario.seed': 'Semilla reproducible para muestreo y backend.',
    'channel.distance_km': 'Longitud física recorrida por la señal.',
    'channel.attenuation_db_km': 'Pérdida óptica por unidad de longitud.',
    'detector.efficiency': 'Probabilidad de registrar un fotón incidente.',
    'detector.dark_count_rate_hz': 'Clicks del detector sin fotón de señal.',
    'post_processing.qber_abort_threshold': 'Umbral diagnóstico para detener el protocolo.',
    'eavesdropper.intercept_probability': 'Fracción de señales interceptadas y reenviadas por Eve.',
  }
  return descriptions[field.key] ?? `Parámetro del bloque ${field.key.split('.')[0]}.`
}

function effectFor(field: CatalogField): string {
  const effects: { [key: string]: string } = {
    'scenario.pulses': 'Aumentarlo mejora la muestra y eleva el coste.',
    'channel.distance_km': 'Más distancia suele reducir detecciones y tasa.',
    'channel.attenuation_db_km': 'Más atenuación reduce la transmitancia.',
    'detector.efficiency': 'Más eficiencia suele aumentar la ganancia.',
    'detector.dark_count_rate_hz': 'Más ruido oscuro puede elevar el QBER.',
    'detector.gate_width_s': 'Una ventana mayor admite más señal y también más ruido.',
    'post_processing.qber_abort_threshold': 'Define la condición de aborto, no una garantía de seguridad.',
  }
  return effects[field.key] ?? (field.sweepable ? 'Puede variarse en un sweep compatible.' : 'Modifica el modelo efectivo del bloque.')
}

function symbolFor(key: string): string {
  const symbols: { [key: string]: string } = {
    'channel.distance_km': 'L',
    'channel.attenuation_db_km': 'α',
    'detector.efficiency': 'ηd',
    'source.mean_photon_number': 'μ',
    'post_processing.qber_abort_threshold': 'Qmax',
  }
  return symbols[key] ?? ''
}

function rangeLabel(field: CatalogField): string {
  if (typeof field.min !== 'number' && typeof field.max !== 'number') return 'según modelo'
  return `${field.min ?? '−∞'}–${field.max ?? '∞'}${field.unit ? ` ${field.unit}` : ''}`
}
