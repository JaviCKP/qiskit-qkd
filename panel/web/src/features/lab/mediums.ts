import type {
  ChannelPayload,
  Catalog,
  DetectorPayload,
  JsonObject,
  ScenarioPayload,
  SourcePayload,
} from '@/api/client'
import type { CurveRecipeId } from '@/features/curves/recipes'
import { defaultScenario } from '@/features/designer/defaultScenario'
import { cloneJson, isRecord, readTarget } from '@/features/shared/scenarioPaths'

export type MediumId =
  | 'ideal'
  | 'fiber'
  | 'vacuum'
  | 'air'
  | 'satellite'
  | 'underwater'
  | 'custom'

export type MediumDefinition = {
  id: MediumId
  label: string
  shortLabel: string
  summary: string
  channelKinds: string[]
  icon: 'sparkles' | 'cable' | 'orbit' | 'cloud' | 'satellite' | 'waves' | 'sliders'
  expectedRange: string
  detectorLabel: string
  realismLabel: string
  defaultCurveRecipeId: CurveRecipeId
  scenario: ScenarioPayload
}

const mediumIds: MediumId[] = [
  'ideal',
  'fiber',
  'vacuum',
  'air',
  'satellite',
  'underwater',
  'custom',
]

const mediumScenarios: Record<MediumId, ScenarioPayload> = {
  ideal: buildScenario('ideal', {
    pulses: 1024,
    source: {
      kind: 'ideal_single_photon',
      emission_probability: 1,
      mean_photon_number: null,
      preparation_error_probability: 0,
      decoy_intensities: [],
    },
    channel: {
      kind: 'ideal',
      distance_km: 0,
      attenuation_db_km: 0,
      fixed_loss_db: 0,
      background_count_rate_hz: 0,
      depolarizing_probability: 0,
      phase_damping_probability: 0,
      polarization_rotation_y_rad: 0,
      polarization_rotation_z_rad: 0,
    },
    detector: {
      kind: 'ideal',
      efficiency: 1,
      dark_count_rate_hz: 0,
      gate_width_s: 1e-9,
      dead_time_s: 0,
      afterpulse_probability: 0,
      readout_error_probability: 0,
    },
  }),
  fiber: buildScenario('fiber', {
    source: {
      kind: 'decoy_weak_coherent',
    },
    channel: {
      kind: 'fiber',
      distance_km: 100,
      attenuation_db_km: 0.2,
      fixed_loss_db: 0,
      background_count_rate_hz: 0,
      pmd_coefficient_ps_sqrt_km: 0.05,
      chromatic_dispersion_ps_nm_km: 17,
      source_spectral_width_nm: 0.1,
    },
    detector: {
      kind: 'threshold',
      efficiency: 0.85,
      dark_count_rate_hz: 10,
      gate_width_s: 1e-9,
    },
  }),
  vacuum: buildScenario('vacuum', {
    source: {
      kind: 'decoy_weak_coherent',
    },
    channel: {
      kind: 'space',
      distance_km: 1000,
      attenuation_db_km: 0,
      fixed_loss_db: 0,
      wavelength_nm: 1550,
      transmitter_aperture_m: 0.12,
      receiver_aperture_m: 1.2,
      beam_divergence_rad: 2e-6,
      atmospheric_extinction_db_km: 0,
      scintillation_sigma: 0,
      pointing_jitter_rad: 1e-6,
      background_count_rate_hz: 5,
    },
    detector: {
      kind: 'threshold',
      efficiency: 0.8,
      dark_count_rate_hz: 5,
      gate_width_s: 1e-9,
    },
  }),
  air: buildScenario('air', {
    source: {
      kind: 'decoy_weak_coherent',
    },
    channel: {
      kind: 'free_space',
      distance_km: 1.5,
      attenuation_db_km: 0,
      fixed_loss_db: 0,
      wavelength_nm: 850,
      transmitter_aperture_m: 0.05,
      receiver_aperture_m: 0.2,
      beam_divergence_rad: 1e-4,
      atmospheric_extinction_db_km: 1,
      scintillation_sigma: 0.3,
      pointing_jitter_rad: 5e-6,
      background_count_rate_hz: 500,
    },
    detector: {
      kind: 'threshold',
      efficiency: 0.65,
      dark_count_rate_hz: 100,
      gate_width_s: 1e-9,
    },
  }),
  satellite: buildScenario('satellite', {
    source: {
      kind: 'decoy_weak_coherent',
    },
    channel: {
      kind: 'free_space',
      distance_km: 500,
      attenuation_db_km: 0,
      fixed_loss_db: 2,
      wavelength_nm: 850,
      transmitter_aperture_m: 0.1,
      receiver_aperture_m: 1,
      beam_divergence_rad: 1e-5,
      atmospheric_extinction_db_km: 0.02,
      scintillation_sigma: 0.12,
      pointing_jitter_rad: 2e-6,
      background_count_rate_hz: 250,
    },
    detector: {
      kind: 'threshold',
      efficiency: 0.7,
      dark_count_rate_hz: 25,
      gate_width_s: 1e-9,
    },
  }),
  underwater: buildScenario('underwater', {
    source: {
      kind: 'decoy_weak_coherent',
    },
    channel: {
      kind: 'underwater',
      distance_km: 0.03,
      attenuation_db_km: 0,
      fixed_loss_db: 0,
      wavelength_nm: 520,
      transmitter_aperture_m: 0.03,
      receiver_aperture_m: 0.08,
      beam_divergence_rad: 1e-3,
      underwater_extinction_m_inv: 0.05,
      underwater_scattering_broadening_ns_per_m: 0.008,
      background_count_rate_hz: 50,
    },
    detector: {
      kind: 'threshold',
      efficiency: 0.6,
      dark_count_rate_hz: 50,
      gate_width_s: 1e-9,
    },
  }),
  custom: buildScenario('custom', {}),
}

export const mediumDefinitions: Record<MediumId, MediumDefinition> = {
  ideal: {
    id: 'ideal',
    label: 'Canal ideal',
    shortLabel: 'Ideal',
    summary: 'Referencia sin pérdidas con fuente, canal y detector ideales.',
    channelKinds: ['ideal'],
    icon: 'sparkles',
    expectedRange: '0 km',
    detectorLabel: 'Detector ideal',
    realismLabel: 'Referencia',
    defaultCurveRecipeId: 'ideal-baseline',
    scenario: mediumScenarios.ideal,
  },
  fiber: {
    id: 'fiber',
    label: 'Fibra telecom',
    shortLabel: 'Fibra',
    summary: 'BB84 con decoys sobre fibra, atenuación realista y bajo ruido oscuro.',
    channelKinds: ['fiber'],
    icon: 'cable',
    expectedRange: '100 km',
    detectorLabel: 'Detector umbral',
    realismLabel: 'Campo',
    defaultCurveRecipeId: 'skr-distance',
    scenario: mediumScenarios.fiber,
  },
  vacuum: {
    id: 'vacuum',
    label: 'Vacío',
    shortLabel: 'Vacío',
    summary: 'Propagación espacial de largo alcance sin extinción atmosférica ni centelleo.',
    channelKinds: ['space', 'deep_space', 'vacuum'],
    icon: 'orbit',
    expectedRange: '1000 km',
    detectorLabel: 'Bajo ruido',
    realismLabel: 'Geometría',
    defaultCurveRecipeId: 'qber-distance',
    scenario: mediumScenarios.vacuum,
  },
  air: {
    id: 'air',
    label: 'Aire urbano',
    shortLabel: 'Aire',
    summary: 'Salto óptico terrestre con extinción, centelleo, apuntamiento y fondo diurno.',
    channelKinds: ['free_space', 'atmospheric'],
    icon: 'cloud',
    expectedRange: '1.5 km',
    detectorLabel: 'Detector umbral',
    realismLabel: 'Atmósfera',
    defaultCurveRecipeId: 'qber-atmosphere',
    scenario: mediumScenarios.air,
  },
  satellite: {
    id: 'satellite',
    label: 'Satélite LEO',
    shortLabel: 'Satélite',
    summary: 'Enlace descendente de espacio libre con distancia LEO, pérdida por apertura, fondo y apuntamiento.',
    channelKinds: ['satellite'],
    icon: 'satellite',
    expectedRange: '500 km',
    detectorLabel: 'Umbral espacial',
    realismLabel: 'Orbital',
    defaultCurveRecipeId: 'gain-pointing',
    scenario: mediumScenarios.satellite,
  },
  underwater: {
    id: 'underwater',
    label: 'Submarino',
    shortLabel: 'Submarino',
    summary: 'Enlace azul-verde de 520 nm bajo el agua con extinción y ensanchamiento por dispersión.',
    channelKinds: ['underwater', 'water', 'marine'],
    icon: 'waves',
    expectedRange: '30 m',
    detectorLabel: 'Detector umbral',
    realismLabel: 'Agua',
    defaultCurveRecipeId: 'gain-water-extinction',
    scenario: mediumScenarios.underwater,
  },
  custom: {
    id: 'custom',
    label: 'Custom experto',
    shortLabel: 'Custom',
    summary: 'Parte del escenario por defecto y deja todos los controles abiertos.',
    channelKinds: [],
    icon: 'sliders',
    expectedRange: 'Manual',
    detectorLabel: 'Manual',
    realismLabel: 'Manual',
    defaultCurveRecipeId: 'custom-axis',
    scenario: mediumScenarios.custom,
  },
}

export const mediumOptions = mediumIds.map((id) => mediumDefinitions[id])

export function scenarioForMedium(id: MediumId): ScenarioPayload {
  return cloneJson(mediumDefinitions[id].scenario)
}

/** Apply scientific medium scenarios received from the versioned catalog.
 * Visual labels/icons/copy remain unchanged and are intentionally not part
 * of the backend metadata.  Missing/legacy metadata leaves the explicit
 * offline scenarios above intact.
 */
export function hydrateMediumScenarios(catalog: Catalog): void {
  if (catalog.metadata_version !== 1 || !catalog.media) return
  for (const media of catalog.media) {
    if (!isMediumId(media.id) || !media.scenario) continue
    mediumDefinitions[media.id].scenario = cloneJson(media.scenario)
    mediumDefinitions[media.id].channelKinds = [...media.channel_kinds]
  }
}

export function inferMediumFromScenario(scenario: JsonObject): MediumId {
  const metadata = readTarget(scenario, 'scenario.metadata')
  if (isRecord(metadata) && isMediumId(metadata.mediumId)) {
    return metadata.mediumId
  }

  const channelKind = readTarget(scenario, 'channel.kind')
  if (typeof channelKind !== 'string') {
    return 'custom'
  }

  switch (channelKind.toLowerCase()) {
    case 'ideal':
      return 'ideal'
    case 'fiber':
      return 'fiber'
    case 'underwater':
    case 'water':
    case 'marine':
      return 'underwater'
    case 'space':
    case 'deep_space':
    case 'vacuum':
      return 'vacuum'
    case 'satellite':
      return 'satellite'
    case 'free_space':
    case 'atmospheric':
      return 'air'
    default:
      return 'custom'
  }
}

function buildScenario(
  mediumId: MediumId,
  updates: {
    pulses?: number
    source?: Partial<SourcePayload>
    channel?: Partial<ChannelPayload>
    detector?: Partial<DetectorPayload>
  },
): ScenarioPayload {
  const scenario = cloneJson(defaultScenario)
  const next: ScenarioPayload = {
    ...scenario,
    metadata: {
      ...scenario.metadata,
      mediumId,
    },
  }

  if (updates.pulses !== undefined) {
    next.pulses = updates.pulses
  }
  if (updates.source) {
    next.source = { ...scenario.source, ...updates.source }
  }
  if (updates.channel) {
    next.channel = { ...scenario.channel, ...updates.channel }
  }
  if (updates.detector) {
    next.detector = { ...scenario.detector, ...updates.detector }
  }
  return next
}


function isMediumId(value: unknown): value is MediumId {
  return typeof value === 'string' && mediumIds.includes(value as MediumId)
}
