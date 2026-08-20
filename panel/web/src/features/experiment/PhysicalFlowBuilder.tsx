import { useEffect, useState, type ReactNode } from 'react'
import { ArrowRight, Clock3, RadioReceiver, Route, Send, SlidersHorizontal } from 'lucide-react'

import type {
  ApiValidationIssue,
  CatalogField,
  CatalogSection,
  ScenarioPayload,
} from '@/api/client'
import { FieldControl } from '@/features/designer/fieldControls'
import { visibleFieldsForMedium } from '@/features/designer/fieldVisibility'
import { Drawer, InfoTip } from '@/components/ui'
import { TemporalPatternBuilder } from '@/features/dynamics/TemporalPatternBuilder'
import { mediumDefinitions, mediumOptions, type MediumId } from '@/features/lab/mediums'
import { readTarget } from '@/features/shared/scenarioPaths'

import { fieldHelp } from './fieldHelp'

type FlowBlock = {
  id: 'emitter' | 'channel' | 'receiver'
  eyebrow: string
  title: string
  description: string
  sections: string[]
  primary: string[]
  accent: string
  Icon: typeof Send
}

const sourcePrimary = [
  'protocol.name',
  'source.kind',
  'source.emission_probability',
  'source.mean_photon_number',
  'source.preparation_error_probability',
  'e91.bell_state',
]

const channelPrimary: Record<MediumId, string[]> = {
  ideal: ['channel.distance_km'],
  fiber: [
    'channel.distance_km',
    'channel.attenuation_db_km',
    'channel.fixed_loss_db',
    'channel.depolarizing_probability',
  ],
  vacuum: [
    'channel.distance_km',
    'channel.beam_divergence_rad',
    'channel.fixed_loss_db',
    'channel.background_count_rate_hz',
  ],
  air: [
    'channel.distance_km',
    'channel.atmospheric_extinction_db_km',
    'channel.scintillation_sigma',
    'channel.background_count_rate_hz',
  ],
  satellite: [
    'channel.distance_km',
    'channel.pointing_jitter_rad',
    'channel.atmospheric_extinction_db_km',
    'channel.background_count_rate_hz',
  ],
  underwater: [
    'channel.distance_km',
    'channel.underwater_extinction_m_inv',
    'channel.underwater_scattering_broadening_ns_per_m',
    'channel.background_count_rate_hz',
  ],
  custom: [
    'channel.kind',
    'channel.distance_km',
    'channel.fixed_loss_db',
    'channel.depolarizing_probability',
  ],
}

const receiverPrimary = [
  'detector.kind',
  'detector.efficiency',
  'detector.dark_count_rate_hz',
  'detector.gate_width_s',
]

export function PhysicalFlowBuilder({
  errors,
  sections,
  scenario,
  mediumId,
  editedFields,
  onChange,
  onSelectMedium,
}: {
  errors: ApiValidationIssue[]
  sections: CatalogSection[]
  scenario: ScenarioPayload
  mediumId: MediumId
  editedFields: string[]
  onChange: (target: string, value: unknown) => void
  onSelectMedium: (mediumId: MediumId) => void
}) {
  const catalogFields = sections.flatMap((section) => section.fields)
  const visibleFields = visibleFieldsForMedium({
    fields: catalogFields,
    mediumId,
    scenario,
    expert: false,
    search: '',
  })
  const visibleByKey = new Map(visibleFields.map((field) => [field.key, field]))
  const [openPanel, setOpenPanel] = useState<FlowBlock['id'] | 'temporal' | null>(null)
  const blocks: FlowBlock[] = [
    {
      id: 'emitter',
      eyebrow: '01 · Alice',
      title: 'Emisor',
      description: 'Qué se envía y con qué protocolo.',
      sections: ['protocol', 'source', 'eavesdropper', 'e91'],
      primary: sourcePrimary,
      accent: 'from-violet/[0.14] to-transparent text-violet',
      Icon: Send,
    },
    {
      id: 'channel',
      eyebrow: '02 · Propagación',
      title: 'Canal',
      description: 'Por dónde viaja la señal y qué la perturba.',
      sections: ['channel', 'timing', 'dynamic'],
      primary: channelPrimary[mediumId],
      accent: 'from-cyan/[0.14] to-transparent text-cyan',
      Icon: Route,
    },
    {
      id: 'receiver',
      eyebrow: '03 · Bob',
      title: 'Receptor',
      description: 'Cómo se detecta y procesa lo recibido.',
      sections: ['detector', 'post_processing'],
      primary: receiverPrimary,
      accent: 'from-success/[0.14] to-transparent text-success',
      Icon: RadioReceiver,
    },
  ]

  const handleChange = (target: string, value: unknown) => {
    if (target === 'protocol.name' && value === 'e91') {
      onChange(target, value)
      onChange('source.kind', 'entangled_pair')
      return
    }
    if (target === 'protocol.name' && value === 'bb84') {
      onChange(target, value)
      if (['bell_pair', 'e91', 'entangled_pair'].includes(scenario.source.kind)) {
        onChange('source.kind', mediumId === 'ideal' ? 'ideal_single_photon' : 'decoy_weak_coherent')
      }
      return
    }
    onChange(target, value)
  }
  const advancedFieldsFor = (block: FlowBlock) => {
    const primaryKeys = new Set(block.primary.filter((key) => visibleByKey.has(key)))
    return visibleFields.filter(
      (field) => block.sections.includes(field.key.split('.')[0]) && !primaryKeys.has(field.key),
    )
  }
  const openedBlock = blocks.find((block) => block.id === openPanel)

  useEffect(() => {
    if (!openPanel) return undefined
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenPanel(null)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [openPanel])

  return (
    <section aria-labelledby="physical-flow-title" className="min-w-0">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-2xs font-semibold uppercase tracking-eyebrow text-cyan">Configura el enlace</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-white" id="physical-flow-title">
            Emisor <span className="text-slate-600">→</span> canal <span className="text-slate-600">→</span> receptor
          </h2>
          <p className="mt-1 text-sm text-slate-400">Sólo aparecen los controles que tienen efecto en el escenario elegido.</p>
        </div>
        <p className="shrink-0 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-slate-400">
          <span className="font-mono font-medium text-slate-200">{visibleFields.length}</span> parámetros compatibles
        </p>
      </div>

      <div className="grid min-w-0 items-start gap-3 xl:grid-cols-[minmax(0,1fr)_28px_minmax(0,1.12fr)_28px_minmax(0,1fr)]">
        {blocks.map((block, index) => {
          const primaryFields = block.primary.map((key) => visibleByKey.get(key)).filter(isPresent)
          const advancedFields = advancedFieldsFor(block)
          return (
            <div className="contents" key={block.id}>
              {index > 0 ? (
                <div aria-hidden="true" className="hidden h-16 items-center justify-center text-slate-600 xl:flex">
                  <ArrowRight size={19} />
                </div>
              ) : null}
              <article className="min-w-0 rounded-panel border border-border bg-surface shadow-panel transition-shadow hover:shadow-lifted">
                <div className={`bg-gradient-to-br ${block.accent} border-b border-border px-4 py-4 sm:px-5`}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-2xs font-semibold uppercase tracking-eyebrow opacity-90">{block.eyebrow}</p>
                      <h3 className="mt-1 text-lg font-semibold tracking-tight text-white">{block.title}</h3>
                      <p className="mt-1 text-sm text-slate-400">{block.description}</p>
                    </div>
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-control border border-current/25 bg-background/60">
                      <block.Icon aria-hidden="true" size={19} />
                    </div>
                  </div>
                </div>

                <div className="space-y-4 p-4 sm:p-5">
                  {block.id === 'channel' ? (
                    <label className="block">
                      <span className="flex items-center gap-1 text-xs font-medium text-slate-300">
                        Medio físico
                        <InfoTip label="Medio físico" text={fieldHelp('channel.kind')} />
                      </span>
                      <select
                        aria-label="Medio físico"
                        className="mt-1.5 h-10 w-full rounded-control border border-border bg-background px-3 text-sm text-white transition-colors hover:border-border-strong focus:border-cyan"
                        onChange={(event) => onSelectMedium(event.target.value as MediumId)}
                        value={mediumId}
                      >
                        {mediumOptions.map((medium) => <option key={medium.id} value={medium.id}>{medium.label}</option>)}
                      </select>
                      <span className="mt-1.5 block text-xs leading-5 text-slate-500">{mediumDefinitions[mediumId].summary}</span>
                    </label>
                  ) : null}

                  <div className="space-y-4">
                    {primaryFields.map((field) => (
                      <CompactField
                        edited={editedFields.includes(field.key)}
                        error={fieldError(errors, field.key)}
                        field={field}
                        key={field.key}
                        onChange={handleChange}
                        scenario={scenario}
                      />
                    ))}
                  </div>

                  {block.id === 'emitter' ? (
                    <SourceEmissionGuide onOpenSettings={() => setOpenPanel('emitter')} scenario={scenario} />
                  ) : null}

                  {advancedFields.length ? (
                    <div className="flex items-center gap-2 border-t border-border pt-3">
                      <button
                        aria-haspopup="dialog"
                        className="group/adv flex min-w-0 flex-1 items-center justify-between gap-3 rounded-control px-2 py-1.5 -mx-2 text-left text-sm font-medium text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white"
                        onClick={() => setOpenPanel(block.id)}
                        type="button"
                      >
                        <span className="flex items-center gap-2"><SlidersHorizontal aria-hidden="true" size={15} /> Más ajustes de {block.title.toLowerCase()}</span>
                        <span className="rounded-full bg-raised px-2 py-0.5 font-mono text-2xs text-slate-400 transition-colors group-hover/adv:bg-overlay group-hover/adv:text-slate-200">
                          {advancedFields.length}
                        </span>
                      </button>
                      <InfoTip label={`Más ajustes de ${block.title.toLowerCase()}`} text={advancedHelp(block.id)} />
                    </div>
                  ) : null}
                  {block.id === 'channel' ? (
                    <div className="flex items-center gap-2 border-t border-border pt-3">
                      <button
                        aria-haspopup="dialog"
                        className="flex min-w-0 flex-1 items-center gap-2 rounded-control px-2 py-1.5 -mx-2 text-left text-sm font-medium text-slate-300 transition-colors hover:bg-white/[0.04] hover:text-white"
                        onClick={() => setOpenPanel('temporal')}
                        type="button"
                      >
                        <Clock3 aria-hidden="true" size={15} /> Variación temporal
                      </button>
                      <InfoTip label="Variación temporal" text={fieldHelp('dynamic.parameter_schedules')} />
                    </div>
                  ) : null}
                </div>
              </article>
            </div>
          )
        })}
      </div>
      {openedBlock ? (
        <SettingsDrawer
          description={`Parámetros compatibles menos frecuentes del ${openedBlock.title.toLowerCase()}.`}
          onClose={() => setOpenPanel(null)}
          title={openedBlock.title}
        >
          {advancedFieldsFor(openedBlock).map((field) => (
            <CompactField
              edited={editedFields.includes(field.key)}
              error={fieldError(errors, field.key)}
              field={field}
              key={field.key}
              onChange={handleChange}
              scenario={scenario}
            />
          ))}
        </SettingsDrawer>
      ) : null}
      {openPanel === 'temporal' ? (
        <SettingsDrawer
          description="Define una variación física en el tiempo sin desplazar el configurador principal."
          onClose={() => setOpenPanel(null)}
          title="Variación temporal"
        >
          <TemporalPatternBuilder onChange={handleChange} scenario={scenario} />
        </SettingsDrawer>
      ) : null}
    </section>
  )
}

function SettingsDrawer({
  title,
  description,
  onClose,
  children,
}: {
  title: string
  description: string
  onClose: () => void
  children: ReactNode
}) {
  return (
    <Drawer description={description} onClose={onClose} open title={`Ajustes avanzados de ${title}`}>
      <div className="space-y-5">{children}</div>
    </Drawer>
  )
}

function CompactField({
  field,
  scenario,
  edited,
  error,
  onChange,
}: {
  field: CatalogField
  scenario: ScenarioPayload
  edited: boolean
  error: string | null
  onChange: (target: string, value: unknown) => void
}) {
  const controlId = `flow-${field.key.replaceAll('.', '-')}`
  const value = readTarget(scenario, field.key) ?? field.default
  const friendlyOptions = friendlySelectOptions(field.key, scenario)
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1">
          <label className="text-xs font-medium text-slate-300" htmlFor={controlId}>{friendlyLabel(field)}</label>
          <InfoTip label={friendlyLabel(field)} text={fieldHelp(field.key)} />
        </span>
        {edited ? (
          <span className="shrink-0 rounded-full bg-cyan/10 px-1.5 py-0.5 text-2xs font-medium uppercase tracking-[0.08em] text-cyan">
            editado
          </span>
        ) : null}
      </div>
      <div className="mt-1.5 flex min-w-0 items-start gap-2">
        {friendlyOptions ? (
          <select
            className="h-9 min-w-0 flex-1 rounded-control border border-border bg-background px-3 text-sm text-white transition-colors hover:border-border-strong focus:border-cyan"
            id={controlId}
            onChange={(event) => onChange(field.key, event.target.value)}
            value={String(value ?? '')}
          >
            {friendlyOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        ) : (
          <FieldControl field={field} id={controlId} onChange={onChange} value={value} />
        )}
        {field.unit ? <span className="mt-2 max-w-16 shrink-0 font-mono text-xs text-slate-500">{field.unit}</span> : null}
      </div>
      {error ? <p className="mt-1.5 text-xs text-danger">{error}</p> : null}
    </div>
  )
}

function friendlySelectOptions(key: string, scenario: ScenarioPayload): Array<{ value: string; label: string }> | null {
  if (key === 'protocol.name') {
    return [
      { value: 'bb84', label: 'BB84 · preparación y medida' },
      { value: 'e91', label: 'E91 · pares entrelazados' },
    ]
  }
  if (key === 'source.kind') {
    if (scenario.protocol.name === 'e91') {
      const options = [{ value: 'entangled_pair', label: 'Par entrelazado' }]
      return includeCurrentOption(options, scenario.source.kind)
    }
    const options = [
      { value: 'ideal_single_photon', label: 'Fotón único ideal' },
      { value: 'weak_coherent', label: 'Fuente coherente débil' },
      { value: 'decoy_weak_coherent', label: 'Coherente débil con decoys' },
    ]
    return includeCurrentOption(options, scenario.source.kind)
  }
  if (key === 'detector.kind') {
    return [
      { value: 'ideal', label: 'Detector ideal' },
      { value: 'threshold', label: 'Detector umbral realista' },
    ]
  }
  if (key === 'eavesdropper.kind') {
    return [
      { value: 'none', label: 'Sin Eve' },
      { value: 'intercept_resend', label: 'Interceptar y reenviar' },
      { value: 'photon_number_splitting', label: 'Photon-number splitting' },
    ]
  }
  if (key === 'detector.double_click_policy') {
    return [
      { value: 'discard', label: 'Descartar el pulso' },
      { value: 'random', label: 'Asignar un bit al azar' },
      { value: 'error', label: 'Contarlo como error' },
    ]
  }
  if (key === 'timing.slot_assignment_policy') {
    return [
      { value: 'discard', label: 'Descartar fuera de ventana' },
      { value: 'nearest', label: 'Asignar a la ranura más cercana' },
    ]
  }
  if (key === 'post_processing.decoy_security_method') {
    return [
      { value: 'none', label: 'Sin estimación decoy' },
      { value: 'vacuum_weak_asymptotic', label: 'Vacío + decoy débil asintótico' },
    ]
  }
  if (key === 'e91.bell_state') {
    return [
      { value: 'psi_minus', label: 'Psi menos · anticorrelacionado' },
      { value: 'phi_plus', label: 'Phi más · correlacionado' },
    ]
  }
  return null
}

function includeCurrentOption(
  options: Array<{ value: string; label: string }>,
  current: string,
): Array<{ value: string; label: string }> {
  if (options.some((option) => option.value === current)) return options
  return [{ value: current, label: current.replaceAll('_', ' ') }, ...options]
}

function friendlyLabel(field: CatalogField): string {
  const labels: Record<string, string> = {
    'protocol.name': 'Protocolo',
    'source.kind': 'Tipo de fuente',
    'source.emission_probability': 'Probabilidad de emisión',
    'source.mean_photon_number': 'Fotones medios por pulso',
    'source.preparation_error_probability': 'Error de preparación',
    'source.decoy_intensities': 'Intensidades de señal y decoy',
    'protocol.basis_choices': 'Bases de medida',
    'channel.distance_km': 'Distancia del enlace',
    'channel.attenuation_db_km': 'Atenuación de la fibra',
    'channel.fixed_loss_db': 'Pérdidas fijas',
    'channel.depolarizing_probability': 'Ruido de despolarización',
    'channel.background_count_rate_hz': 'Luz de fondo',
    'channel.atmospheric_extinction_db_km': 'Extinción atmosférica',
    'channel.scintillation_sigma': 'Centelleo',
    'channel.pointing_jitter_rad': 'Error de apuntamiento',
    'channel.underwater_extinction_m_inv': 'Turbidez / extinción del agua',
    'channel.underwater_scattering_broadening_ns_per_m': 'Dispersión del agua',
    'channel.kind': 'Modelo de canal',
    'channel.wavelength_nm': 'Longitud de onda',
    'channel.transmitter_aperture_m': 'Apertura del emisor',
    'channel.receiver_aperture_m': 'Apertura del receptor',
    'channel.beam_divergence_rad': 'Divergencia del haz',
    'channel.phase_damping_probability': 'Pérdida de coherencia de fase',
    'channel.polarization_rotation_y_rad': 'Rotación de polarización Y',
    'channel.polarization_rotation_z_rad': 'Rotación de polarización Z',
    'channel.pmd_coefficient_ps_sqrt_km': 'Dispersión por modo de polarización',
    'channel.chromatic_dispersion_ps_nm_km': 'Dispersión cromática',
    'channel.source_spectral_width_nm': 'Ancho espectral de la fuente',
    'channel.polarization_dependent_loss_db': 'Pérdida según polarización',
    'channel.pdl_axis_basis': 'Base de la pérdida por polarización',
    'channel.pdl_axis_bit': 'Estado afectado por la pérdida',
    'channel.classical_channel_power_mw': 'Potencia del canal clásico',
    'channel.raman_coefficient_hz_mw_km': 'Coeficiente de ruido Raman',
    'channel.raman_filter_isolation_db': 'Aislamiento del filtro Raman',
    'detector.kind': 'Tipo de detector',
    'detector.efficiency': 'Eficiencia de detección',
    'detector.dark_count_rate_hz': 'Ruido oscuro',
    'detector.gate_width_s': 'Ventana de detección',
    'detector.dead_time_s': 'Tiempo muerto',
    'detector.afterpulse_probability': 'Probabilidad de afterpulse',
    'detector.readout_error_probability': 'Error de lectura',
    'detector.double_click_policy': 'Doble detección',
    'timing.propagation_delay_s': 'Retardo de propagación',
    'timing.jitter_std_s': 'Jitter temporal',
    'timing.clock_offset_s': 'Desfase de reloj',
    'timing.clock_drift_ppm': 'Deriva de reloj',
    'timing.slot_assignment_policy': 'Asignación de ranura temporal',
    'post_processing.sifting_enabled': 'Cribado de bases',
    'post_processing.qber_abort_threshold': 'Umbral de aborto QBER',
    'post_processing.qber_sample_fraction': 'Muestra para estimar QBER',
    'post_processing.error_correction_efficiency': 'Eficiencia de corrección',
    'post_processing.reconciliation_block_size': 'Tamaño de bloque de reconciliación',
    'post_processing.privacy_amplification_enabled': 'Amplificación de privacidad',
    'post_processing.decoy_security_estimation_enabled': 'Estimación de seguridad decoy',
    'post_processing.decoy_security_method': 'Método de estimación decoy',
    'eavesdropper.kind': 'Modelo de Eve',
    'eavesdropper.intercept_probability': 'Fracción interceptada',
    'eavesdropper.pns_split_probability': 'Probabilidad de separar un fotón',
    'eavesdropper.pns_block_single_photon_probability': 'Bloqueo de pulsos de un fotón',
    'e91.bell_state': 'Estado de Bell',
    'e91.alice_angles_rad': 'Ángulos de Alice',
    'e91.bob_angles_rad': 'Ángulos de Bob',
    'e91.key_setting_pairs': 'Ajustes usados para clave',
    'e91.chsh_terms': 'Términos de CHSH',
    'e91.bob_key_bit_flip': 'Invertir bit de Bob',
    'e91.chsh_estimation_enabled': 'Estimar CHSH',
    'dynamic.parameter_schedules': 'Agenda de variación temporal',
    'scenario.pulses': 'Pulsos',
    'scenario.clock_rate_hz': 'Reloj de emisión',
    'scenario.seed': 'Semilla reproducible',
    'scenario.event_sample_size': 'Muestra de eventos',
    'scenario.store_full_event_log': 'Conservar todos los eventos',
  }
  return labels[field.key] ?? field.label_es
}

function fieldError(errors: ApiValidationIssue[], fieldKey: string): string | null {
  return errors.find((error) => error.loc === fieldKey)?.msg ?? null
}

function SourceEmissionGuide({ scenario, onOpenSettings }: { scenario: ScenarioPayload; onOpenSettings: () => void }) {
  const isDecoy = scenario.source.kind === 'decoy_weak_coherent'
  const isCoherent = isDecoy || scenario.source.kind === 'weak_coherent'
  if (!isCoherent) return null
  const intensities = scenario.source.decoy_intensities
  return (
    <div className="rounded-control border border-violet/25 bg-violet/[0.06] p-3 text-xs">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-violet">La emisión se controla con intensidades μ</p>
          <p className="mt-1 leading-5 text-slate-400">
            {isDecoy
              ? `Esta fuente elige entre ${intensities.length} intensidades de señal/decoy; por eso la probabilidad de emisión ideal no se aplica.`
              : 'En una fuente coherente, μ determina la estadística de fotones; la probabilidad de emisión ideal no se aplica.'}
          </p>
        </div>
        <InfoTip label="Control de emisión coherente" text={fieldHelp(isDecoy ? 'source.decoy_intensities' : 'source.mean_photon_number')} />
      </div>
      {isDecoy ? (
        <button className="mt-2 font-medium text-violet transition-colors hover:text-white" onClick={onOpenSettings} type="button">
          Editar intensidades y probabilidades →
        </button>
      ) : null}
    </div>
  )
}

function advancedHelp(block: FlowBlock['id']): string {
  if (block === 'emitter') return 'Incluye intensidades decoy, modelos de Eve y opciones de E91 que sólo aparecen cuando tienen efecto.'
  if (block === 'channel') return 'Incluye pérdidas, polarización, dispersión, ruido y timing compatibles con el medio elegido.'
  return 'Incluye tiempo muerto, afterpulses, lectura y postprocesado compatibles con el detector y el protocolo.'
}

function isPresent<T>(value: T | undefined): value is T {
  return value !== undefined
}
