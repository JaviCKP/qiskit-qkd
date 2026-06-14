import type { AxisRequest } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'

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
  metric: string
  axis: AxisRequest
  series: AxisRequest | null
  repeats: number
}

export type CurveRecipe = {
  id: CurveRecipeId
  label: string
  question: string
  metric: string
  defaultAxis: AxisRequest
  preferredMedia: MediumId[]
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
    'Como cambia el error cuando solo aumentamos el numero de pulsos?',
    'qber',
    axis('scenario.pulses', 256, 8192, 8, 'log'),
    ['ideal'],
  ),
  'skr-distance': recipe(
    'skr-distance',
    'Clave secreta frente a distancia',
    'Cuanta distancia aguanta el enlace antes de perder clave util?',
    'secret_key_rate_bps',
    axis('channel.distance_km', 0, 120, 25, 'linear'),
    ['fiber'],
  ),
  'qber-distance': recipe(
    'qber-distance',
    'Error frente a distancia',
    'Como sube el QBER al alargar el enlace?',
    'qber',
    axis('channel.distance_km', 0, 120, 25, 'linear'),
    ['fiber', 'vacuum', 'air', 'satellite', 'underwater'],
  ),
  'qber-dark-counts': recipe(
    'qber-dark-counts',
    'Ruido oscuro del detector',
    'Cuanto error introducen los conteos oscuros?',
    'qber',
    axis('detector.dark_count_rate_hz', 0, 1000, 21, 'linear'),
    allMedia,
  ),
  'mean-photon-number': recipe(
    'mean-photon-number',
    'Intensidad de la fuente',
    'Que intensidad produce mas clave sin disparar demasiado error?',
    'secret_key_rate_bps',
    axis('source.mean_photon_number', 0.05, 1, 20, 'linear'),
    ['fiber', 'vacuum', 'air', 'satellite', 'underwater', 'custom'],
  ),
  'qber-eve': recipe(
    'qber-eve',
    'Ataque intercept-resend',
    'Cuando se vuelve visible una Eve que intercepta parte de la senal?',
    'qber',
    axis('eavesdropper.intercept_probability', 0, 1, 21, 'linear'),
    ['ideal', 'fiber', 'custom'],
  ),
  'chsh-depolarization': recipe(
    'chsh-depolarization',
    'CHSH con despolarizacion',
    'Cuanto ruido rompe la ventaja Bell?',
    'chsh_s',
    axis('channel.depolarizing_probability', 0, 0.5, 21, 'linear'),
    ['ideal', 'vacuum', 'custom'],
  ),
  'gain-pointing': recipe(
    'gain-pointing',
    'Apuntamiento del enlace',
    'Cuanta ganancia perdemos al empeorar el apuntamiento?',
    'gain',
    axis('channel.pointing_jitter_rad', 0, 0.00001, 21, 'linear'),
    ['satellite', 'air', 'vacuum'],
  ),
  'qber-atmosphere': recipe(
    'qber-atmosphere',
    'Extincion atmosferica',
    'Como afecta la atmosfera al error observado?',
    'qber',
    axis('channel.atmospheric_extinction_db_km', 0, 3, 21, 'linear'),
    ['air', 'satellite'],
  ),
  'gain-water-extinction': recipe(
    'gain-water-extinction',
    'Extincion bajo el agua',
    'Cuanta ganancia se pierde en agua mas turbia?',
    'gain',
    axis('channel.underwater_extinction_m_inv', 0.01, 0.2, 20, 'linear'),
    ['underwater'],
  ),
  'metrics-time': recipe(
    'metrics-time',
    'Ventana temporal',
    'Como cambia la deteccion al ensanchar el jitter temporal?',
    'raw_detection_rate_hz',
    axis('timing.jitter_std_s', 0, 0.000000005, 21, 'linear'),
    ['fiber', 'air', 'satellite', 'underwater', 'custom'],
  ),
  'custom-axis': recipe(
    'custom-axis',
    'Eje personalizado',
    'Elige el parametro de barrido desde el catalogo.',
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
    metric: selected.metric,
    axis: cloneAxis(axisForRecipe(selected, mediumId)),
    series: null,
    repeats: 1,
  }
}

export function describeCurveRequest(request: CurveRequest): string {
  const values = request.axis.values

  if (Array.isArray(values)) {
    return `Barrido de ${humanTarget(request.axis.target)} con ${values.length} valores.`
  }

  const unit = unitForTarget(request.axis.target)
  const unitSuffix = unit ? ` ${unit}` : ''

  return `Barrido de ${humanTarget(request.axis.target)} de ${formatNumber(
    values.start,
  )} a ${formatNumber(values.stop)}${unitSuffix} en ${values.steps} puntos.`
}

function recipe(
  id: CurveRecipeId,
  label: string,
  question: string,
  metric: string,
  defaultAxis: AxisRequest,
  preferredMedia: MediumId[],
): CurveRecipe {
  return { id, label, question, metric, defaultAxis, preferredMedia }
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

function humanTarget(target: string): string {
  switch (target) {
    case 'scenario.pulses':
      return 'numero de pulsos'
    case 'channel.distance_km':
      return 'distancia de fibra'
    case 'detector.dark_count_rate_hz':
      return 'conteos oscuros'
    case 'source.mean_photon_number':
      return 'numero medio de fotones'
    case 'eavesdropper.intercept_probability':
      return 'probabilidad de interceptacion'
    case 'channel.depolarizing_probability':
      return 'probabilidad de despolarizacion'
    case 'channel.pointing_jitter_rad':
      return 'jitter de apuntamiento'
    case 'channel.atmospheric_extinction_db_km':
      return 'extincion atmosferica'
    case 'channel.underwater_extinction_m_inv':
      return 'extincion bajo el agua'
    case 'timing.jitter_std_s':
      return 'jitter temporal'
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
      return 's'
    default:
      return null
  }
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? value.toString() : String(value)
}
