import type { AxisRequest, JsonObject, ScenarioPayload } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'
import { cloneJson, isRecord, readTarget } from '@/features/shared/scenarioPaths'

export type CurveRecipeId =
  | 'ideal-baseline'
  | 'skr-distance'
  | 'qber-distance'
  | 'qber-dark-counts'
  | 'mean-photon-number'
  | 'qber-eve'
  | 'chsh-depolarization'
  | 'gain-pointing'
  | 'qber-atmosphere'
  | 'gain-water-extinction'
  | 'metrics-time'
  | 'custom-axis'

export type CurveRequest = {
  recipeId: CurveRecipeId
  label: string
  question: string
  metric: string
  axis: AxisRequest
  series: AxisRequest | null
  repeats: number
  scenarioPatch: { [section: string]: JsonObject } | null
  changes: string[]
  fixed: string[]
  requirements: string[]
  applicability: CurveApplicability
}

export type CurveApplicability = {
  protocols?: string[]
  sourceKinds?: string[]
  channelKinds?: string[]
  requiresVaryingDynamics?: boolean
}

export type CurveApplicabilityResult = {
  applicable: boolean
  reasons: string[]
}

export type CurveRecipe = {
  id: CurveRecipeId
  label: string
  question: string
  metric: string
  defaultAxis: AxisRequest
  preferredMedia: MediumId[]
  scenarioPatch: { [section: string]: JsonObject } | null
  changes: string[]
  fixed: string[]
  requirements: string[]
  applicability: CurveApplicability
}

const allMedia: MediumId[] = [
  'ideal',
  'fiber',
  'vacuum',
  'air',
  'satellite',
  'underwater',
  'custom',
]

const recipesById: Record<CurveRecipeId, CurveRecipe> = {
  'ideal-baseline': recipe(
    'ideal-baseline',
    'Linea base ideal',
    '¿Cómo cambia el error cuando solo aumentamos el número de pulsos?',
    'qber',
    axis('scenario.pulses', 256, 8192, 8, 'log'),
    ['ideal'],
    { protocol: { name: 'bb84' } },
  ),
  'skr-distance': recipe(
    'skr-distance',
    'Tasa de clave estimada frente a distancia',
    '¿Cómo cambia la tasa de clave estimada al aumentar la distancia?',
    'secret_key_rate_bps',
    axis('channel.distance_km', 0, 120, 25, 'linear'),
    ['fiber'],
    { protocol: { name: 'bb84' } },
  ),
  'qber-distance': recipe(
    'qber-distance',
    'Error frente a distancia',
    '¿Cómo sube el QBER al alargar el enlace?',
    'qber',
    axis('channel.distance_km', 0, 120, 25, 'linear'),
    ['fiber', 'vacuum', 'air', 'satellite', 'underwater'],
    { protocol: { name: 'bb84' } },
  ),
  'qber-dark-counts': recipe(
    'qber-dark-counts',
    'Ruido oscuro del detector',
    '¿Cuánto error introducen los conteos oscuros?',
    'qber',
    axis('detector.dark_count_rate_hz', 0, 1000, 21, 'linear'),
    allMedia,
    { protocol: { name: 'bb84' } },
  ),
  'mean-photon-number': recipe(
    'mean-photon-number',
    'Intensidad de la fuente',
    'Que intensidad produce mas clave sin disparar demasiado error?',
    'secret_key_rate_bps',
    axis('source.mean_photon_number', 0.05, 1, 20, 'linear'),
    ['fiber', 'vacuum', 'air', 'satellite', 'underwater', 'custom'],
    {
      protocol: { name: 'bb84' },
      source: {
        kind: 'weak_coherent',
        mean_photon_number: 0.5,
        decoy_intensities: [],
      },
      post_processing: {
        decoy_security_estimation_enabled: false,
        decoy_security_method: 'none',
      },
    },
    {
      changes: [
        'Convierte la fuente en coherente débil de intensidad escalar.',
        'Vacía las intensidades decoy para que el número medio barrido sea efectivo.',
      ],
      fixed: ['Mantiene el canal, el detector y el número de pulsos del escenario.'],
      requirements: [
        'La estimación decoy queda desactivada: esta curva es un diagnóstico asintótico del modelo escalar.',
      ],
      applicability: { protocols: ['bb84'], sourceKinds: ['weak_coherent'] },
    },
  ),
  'qber-eve': recipe(
    'qber-eve',
    'Ataque intercept-resend',
    'Cuando se vuelve visible una Eve que intercepta parte de la senal?',
    'qber',
    axis('eavesdropper.intercept_probability', 0, 1, 11, 'linear'),
    ['ideal', 'fiber', 'custom'],
    { protocol: { name: 'bb84' }, eavesdropper: { kind: 'intercept_resend' } },
  ),
  'chsh-depolarization': recipe(
    'chsh-depolarization',
    'CHSH con despolarizacion',
    '¿Cómo cambia el CHSH observado al aumentar el ruido?',
    'chsh_s',
    axis('channel.depolarizing_probability', 0, 0.5, 21, 'linear'),
    ['ideal', 'vacuum', 'custom'],
    {
      protocol: { name: 'e91' },
      source: { kind: 'entangled_pair' },
    },
  ),
  'gain-pointing': recipe(
    'gain-pointing',
    'Apuntamiento del enlace',
    'Cuanta ganancia perdemos al empeorar el apuntamiento?',
    'gain',
    axis('channel.pointing_jitter_rad', 0, 0.00001, 21, 'linear'),
    ['satellite', 'air'],
    { protocol: { name: 'bb84' } },
    {
      requirements: [
        'Requiere un canal free_space, atmospheric o satellite que consuma pointing_jitter_rad.',
      ],
      applicability: {
        protocols: ['bb84'],
        channelKinds: ['free_space', 'atmospheric', 'satellite'],
      },
    },
  ),
  'qber-atmosphere': recipe(
    'qber-atmosphere',
    'Extincion atmosferica',
    '¿Cómo afecta la atmósfera al error observado?',
    'qber',
    axis('channel.atmospheric_extinction_db_km', 0, 3, 21, 'linear'),
    ['air', 'satellite'],
    { protocol: { name: 'bb84' } },
  ),
  'gain-water-extinction': recipe(
    'gain-water-extinction',
    'Extincion bajo el agua',
    'Cuanta ganancia se pierde en agua mas turbia?',
    'gain',
    axis('channel.underwater_extinction_m_inv', 0.01, 0.2, 20, 'linear'),
    ['underwater'],
    { protocol: { name: 'bb84' } },
  ),
  'metrics-time': recipe(
    'metrics-time',
    'Ventana temporal',
    '¿Cómo responde la detección cuando la pérdida aumenta realmente durante la ventana?',
    'raw_detection_rate_hz',
    axis('time_s', 0, 0.001, 8, 'linear'),
    ['fiber', 'air', 'satellite', 'underwater', 'custom'],
    {
      protocol: { name: 'bb84' },
      dynamic: {
        parameter_schedules: [
          {
            target: 'channel.fixed_loss_db',
            profile: {
              kind: 'linear',
              start_s: 0,
              end_s: 0.001,
              start_value: 0,
              end_value: 8,
            },
          },
        ],
      },
    },
    {
      changes: [
        'Aplica una rampa física de pérdida fija de 0 a 8 dB durante 1 ms.',
        'Muestrea la tasa bruta de detección a lo largo de esa misma ventana.',
      ],
      fixed: [
        'Mantiene fuente, detector y geometría del canal; el muestreo aleatorio sigue variando por punto.',
      ],
      requirements: [
        'Requiere al menos una agenda dinámica no constante que cambie un parámetro físico.',
        'Sin esa agenda, time_s sólo cambia el punto de evaluación y la semilla derivada; no demuestra una causa temporal.',
      ],
      applicability: { protocols: ['bb84'], requiresVaryingDynamics: true },
    },
  ),
  'custom-axis': recipe(
    'custom-axis',
    'Eje personalizado',
    'Elige el parámetro de barrido desde el catálogo.',
    'qber',
    axis('channel.distance_km', 0, 120, 25, 'linear'),
    allMedia,
  ),
}

export const curveRecipes: CurveRecipe[] = Object.values(recipesById)

export function buildCurveRequest(
  recipeId: CurveRecipeId,
  mediumId: MediumId,
): CurveRequest {
  const selected = recipesById[recipeId]

  return {
    recipeId,
    label: selected.label,
    question: selected.question,
    metric: selected.metric,
    axis: cloneAxis(axisForRecipe(selected, mediumId)),
    series: null,
    repeats: 1,
    scenarioPatch: cloneScenarioPatch(selected.scenarioPatch),
    changes: [...selected.changes],
    fixed: [...selected.fixed],
    requirements: [...selected.requirements],
    applicability: cloneJson(selected.applicability),
  }
}

export function applyCurveScenarioPatch(
  scenario: ScenarioPayload,
  patch: { [section: string]: JsonObject } | null,
): ScenarioPayload {
  const next = cloneJson(scenario)
  if (patch === null) {
    return next
  }

  for (const [section, values] of Object.entries(patch)) {
    if (section === 'scenario') {
      Object.assign(next, cloneJson(values))
      continue
    }
    const current = next[section]
    next[section] = isRecord(current)
      ? { ...current, ...cloneJson(values) }
      : cloneJson(values)
  }
  return next
}

export function isCurveRequestApplicable(
  request: CurveRequest,
  scenario: ScenarioPayload,
): CurveApplicabilityResult {
  const effectiveScenario = applyCurveScenarioPatch(scenario, request.scenarioPatch)
  const reasons: string[] = []
  const protocol = readString(effectiveScenario, 'protocol.name')
  const sourceKind = readString(effectiveScenario, 'source.kind')
  const channelKind = readString(effectiveScenario, 'channel.kind')

  if (
    request.applicability.protocols?.length &&
    (!protocol || !request.applicability.protocols.includes(protocol))
  ) {
    reasons.push(`Requiere protocolo ${request.applicability.protocols.join(' o ')}.`)
  }
  if (
    request.applicability.sourceKinds?.length &&
    (!sourceKind || !request.applicability.sourceKinds.includes(sourceKind))
  ) {
    reasons.push(`Requiere fuente ${request.applicability.sourceKinds.join(' o ')}.`)
  }
  if (
    request.applicability.channelKinds?.length &&
    (!channelKind || !request.applicability.channelKinds.includes(channelKind))
  ) {
    reasons.push(`El canal ${channelKind ?? 'no definido'} no consume este parámetro.`)
  }
  if (request.applicability.requiresVaryingDynamics) {
    const [start, stop] = axisBounds(request.axis)
    if (!hasPhysicalDynamicVariation(effectiveScenario, start, stop)) {
      reasons.push('Requiere una agenda dinámica que cambie un parámetro físico en la ventana.')
    }
  }

  return { applicable: reasons.length === 0, reasons }
}

export function hasPhysicalDynamicVariation(
  scenario: ScenarioPayload,
  axisStart: number,
  axisStop: number,
): boolean {
  const dynamic = scenario.dynamic
  if (!isRecord(dynamic) || !Array.isArray(dynamic.parameter_schedules)) {
    return false
  }

  const windowStart = Math.min(axisStart, axisStop)
  const windowStop = Math.max(axisStart, axisStop)
  if (!Number.isFinite(windowStart) || !Number.isFinite(windowStop) || windowStop <= windowStart) {
    return false
  }

  return dynamic.parameter_schedules.some((candidate) => {
    if (!isRecord(candidate) || typeof candidate.target !== 'string' || !isRecord(candidate.profile)) {
      return false
    }
    const profile = candidate.profile
    const scheduleStart = finiteNumber(profile.start_s) ?? windowStart
    const scheduleStop = finiteNumber(profile.end_s) ?? windowStop
    const overlapStart = Math.max(windowStart, Math.min(scheduleStart, scheduleStop))
    const overlapStop = Math.min(windowStop, Math.max(scheduleStart, scheduleStop))
    if (overlapStop <= overlapStart) {
      return false
    }

    if (profile.kind === 'linear' || profile.kind === 'exponential') {
      const startValue = finiteNumber(profile.start_value)
      const endValue = finiteNumber(profile.end_value)
      return startValue !== null && endValue !== null && numbersDiffer(startValue, endValue)
    }

    if (profile.kind === 'constant') {
      const value = finiteNumber(profile.value)
      const baseValue = finiteNumber(readTarget(scenario, candidate.target))
      const coversWindow = scheduleStart <= windowStart && scheduleStop >= windowStop
      return (
        value !== null &&
        baseValue !== null &&
        numbersDiffer(value, baseValue) &&
        !coversWindow
      )
    }

    const values = Array.isArray(profile.values)
      ? profile.values.map(finiteNumber).filter((value): value is number => value !== null)
      : []
    return values.some((value) => numbersDiffer(value, values[0] ?? value))
  })
}

export function describeCurveRequest(request: CurveRequest): string {
  const values = request.axis.values

  if (Array.isArray(values)) {
    const valueLabel = values.length === 1 ? 'valor' : 'valores'
    return `Barrido de ${humanTarget(request.axis.target)} con ${values.length} ${valueLabel}.`
  }

  const unit = unitForTarget(request.axis.target)
  const unitSuffix = unit ? ` ${unit}` : ''
  const pointLabel = values.steps === 1 ? 'punto' : 'puntos'

  return `Barrido de ${humanTarget(request.axis.target)} de ${formatNumber(
    values.start,
  )} a ${formatNumber(values.stop)}${unitSuffix} en ${values.steps} ${pointLabel}.`
}

export function curveMetricLabel(metric: string): string {
  const labels: Record<string, string> = {
    chsh_s: 'CHSH observado',
    gain: 'Ganancia',
    qber: 'QBER observado',
    raw_detection_rate_hz: 'Tasa bruta de detección',
    secret_key_rate_bps: 'Tasa de clave estimada',
  }
  return labels[metric] ?? metric
}

function recipe(
  id: CurveRecipeId,
  label: string,
  question: string,
  metric: string,
  defaultAxis: AxisRequest,
  preferredMedia: MediumId[],
  scenarioPatch: { [section: string]: JsonObject } | null = null,
  metadata: Partial<
    Pick<CurveRecipe, 'changes' | 'fixed' | 'requirements' | 'applicability'>
  > = {},
): CurveRecipe {
  const defaultChanges = [`Varía ${humanTarget(defaultAxis.target)} en el eje de la curva.`]
  const defaultFixed = [
    'Mantiene fijos los demás parámetros de fuente, canal, detector y posprocesado.',
  ]
  const defaultRequirements = [
    `El modelo activo debe consumir ${humanTarget(defaultAxis.target)}.`,
  ]
  return {
    id,
    label,
    question,
    metric,
    defaultAxis,
    preferredMedia,
    scenarioPatch,
    changes: metadata.changes ?? defaultChanges,
    fixed: metadata.fixed ?? defaultFixed,
    requirements: metadata.requirements ?? defaultRequirements,
    applicability:
      metadata.applicability ?? applicabilityFor(defaultAxis.target, scenarioPatch),
  }
}

function axis(
  target: string,
  start: number,
  stop: number,
  steps: number,
  scale: 'linear' | 'log',
): AxisRequest {
  return {
    target,
    values: { start, stop, steps, scale },
  }
}

function axisForRecipe(recipeConfig: CurveRecipe, mediumId: MediumId): AxisRequest {
  if (recipeConfig.id !== 'qber-distance') {
    return recipeConfig.defaultAxis
  }

  switch (mediumId) {
    case 'air':
      return axis('channel.distance_km', 0, 5, 25, 'linear')
    case 'satellite':
    case 'vacuum':
      return axis('channel.distance_km', 0, 1000, 25, 'linear')
    case 'underwater':
      return axis('channel.distance_km', 0, 0.1, 25, 'linear')
    default:
      return recipeConfig.defaultAxis
  }
}

function cloneAxis(request: AxisRequest): AxisRequest {
  return {
    target: request.target,
    values: Array.isArray(request.values) ? [...request.values] : { ...request.values },
  }
}

function cloneScenarioPatch(
  patch: { [section: string]: JsonObject } | null,
): { [section: string]: JsonObject } | null {
  return patch === null ? null : cloneJson(patch)
}

function applicabilityFor(
  target: string,
  scenarioPatch: { [section: string]: JsonObject } | null,
): CurveApplicability {
  const applicability: CurveApplicability = {}
  const protocol = scenarioPatch?.protocol?.name
  const sourceKind = scenarioPatch?.source?.kind

  if (typeof protocol === 'string') {
    applicability.protocols = [protocol]
  }
  if (typeof sourceKind === 'string') {
    applicability.sourceKinds = [sourceKind]
  }

  if (target === 'channel.atmospheric_extinction_db_km') {
    applicability.channelKinds = ['free_space', 'atmospheric', 'satellite']
  } else if (target === 'channel.underwater_extinction_m_inv') {
    applicability.channelKinds = ['underwater', 'water', 'marine']
  }

  return applicability
}

function axisBounds(axisRequest: AxisRequest): [number, number] {
  if (!Array.isArray(axisRequest.values)) {
    return [axisRequest.values.start, axisRequest.values.stop]
  }
  const numericValues = axisRequest.values
    .map(finiteNumber)
    .filter((value): value is number => value !== null)
  if (numericValues.length === 0) {
    return [Number.NaN, Number.NaN]
  }
  return [Math.min(...numericValues), Math.max(...numericValues)]
}

function readString(scenario: ScenarioPayload, target: string): string | null {
  const value = readTarget(scenario, target)
  return typeof value === 'string' ? value : null
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function numbersDiffer(left: number, right: number): boolean {
  const tolerance = Number.EPSILON * Math.max(1, Math.abs(left), Math.abs(right)) * 8
  return Math.abs(left - right) > tolerance
}

function humanTarget(target: string): string {
  switch (target) {
    case 'scenario.pulses':
      return 'número de pulsos'
    case 'channel.distance_km':
      return 'distancia de fibra'
    case 'detector.dark_count_rate_hz':
      return 'conteos oscuros'
    case 'source.mean_photon_number':
      return 'número medio de fotones'
    case 'eavesdropper.intercept_probability':
      return 'probabilidad de interceptacion'
    case 'channel.depolarizing_probability':
      return 'probabilidad de despolarizacion'
    case 'channel.pointing_jitter_rad':
      return 'jitter de apuntamiento'
    case 'channel.atmospheric_extinction_db_km':
      return 'extinción atmosférica'
    case 'channel.underwater_extinction_m_inv':
      return 'extinción bajo el agua'
    case 'timing.jitter_std_s':
      return 'jitter temporal'
    case 'time_s':
      return 'tiempo'
    default:
      return target
  }
}

function unitForTarget(target: string): string | null {
  switch (target) {
    case 'channel.distance_km':
      return 'km'
    case 'detector.dark_count_rate_hz':
      return 'Hz'
    case 'channel.pointing_jitter_rad':
      return 'rad'
    case 'channel.atmospheric_extinction_db_km':
      return 'dB/km'
    case 'channel.underwater_extinction_m_inv':
      return 'm^-1'
    case 'timing.jitter_std_s':
    case 'time_s':
      return 's'
    default:
      return null
  }
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? value.toString() : String(value)
}
