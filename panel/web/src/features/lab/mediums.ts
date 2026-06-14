import type { ScenarioPayload } from '@/api/client'
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
  accentClass: string
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
    distanceScheduleValue: 0,
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
      wavelength_nm: 1550,
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
    distanceScheduleValue: 100,
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
    distanceScheduleValue: 1000,
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
    distanceScheduleValue: 1.5,
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
    distanceScheduleValue: 500,
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
    distanceScheduleValue: 0.03,
  }),
  custom: buildScenario('custom', {}),
}

export const mediumDefinitions: Record<MediumId, MediumDefinition> = {
  ideal: {
    id: 'ideal',
    label: 'Ideal laboratory channel',
    shortLabel: 'Ideal',
    summary: 'Lossless baseline with an ideal source, clean channel, and ideal detector.',
    channelKinds: ['ideal'],
    icon: 'sparkles',
    accentClass: 'border-emerald-400 bg-emerald-50 text-emerald-900',
    expectedRange: '0 km reference',
    detectorLabel: 'Ideal detector',
    realismLabel: 'Baseline',
    defaultCurveRecipeId: 'ideal-baseline',
    scenario: mediumScenarios.ideal,
  },
  fiber: {
    id: 'fiber',
    label: 'Telecom fiber',
    shortLabel: 'Fiber',
    summary: 'Decoy-state BB84 over 1550 nm fiber with realistic attenuation and low dark counts.',
    channelKinds: ['fiber'],
    icon: 'cable',
    accentClass: 'border-sky-400 bg-sky-50 text-sky-900',
    expectedRange: '100 km spool',
    detectorLabel: 'Threshold detector',
    realismLabel: 'Field-like',
    defaultCurveRecipeId: 'skr-distance',
    scenario: mediumScenarios.fiber,
  },
  vacuum: {
    id: 'vacuum',
    label: 'Vacuum line of sight',
    shortLabel: 'Vacuum',
    summary: 'Long-range space propagation without atmospheric extinction or scintillation.',
    channelKinds: ['space', 'deep_space', 'vacuum'],
    icon: 'orbit',
    accentClass: 'border-violet-400 bg-violet-50 text-violet-900',
    expectedRange: '1000 km optical path',
    detectorLabel: 'Low-noise threshold',
    realismLabel: 'Geometry-limited',
    defaultCurveRecipeId: 'gain-pointing',
    scenario: mediumScenarios.vacuum,
  },
  air: {
    id: 'air',
    label: 'Urban air link',
    shortLabel: 'Air',
    summary: 'Short free-space optical hop with extinction, scintillation, pointing, and daylight background.',
    channelKinds: ['free_space', 'atmospheric'],
    icon: 'cloud',
    accentClass: 'border-amber-400 bg-amber-50 text-amber-950',
    expectedRange: '1.5 km terrestrial',
    detectorLabel: 'Threshold detector',
    realismLabel: 'Weather-sensitive',
    defaultCurveRecipeId: 'qber-atmosphere',
    scenario: mediumScenarios.air,
  },
  satellite: {
    id: 'satellite',
    label: 'LEO satellite pass',
    shortLabel: 'Satellite',
    summary: 'Free-space downlink with LEO-scale distance, aperture loss, background, and tight pointing.',
    channelKinds: ['satellite'],
    icon: 'satellite',
    accentClass: 'border-indigo-400 bg-indigo-50 text-indigo-900',
    expectedRange: '500 km slant path',
    detectorLabel: 'Space-ready threshold',
    realismLabel: 'LEO-ish',
    defaultCurveRecipeId: 'gain-pointing',
    scenario: mediumScenarios.satellite,
  },
  underwater: {
    id: 'underwater',
    label: 'Underwater blue-green',
    shortLabel: 'Water',
    summary: 'Short 520 nm underwater link with clear-water extinction and scattering broadening.',
    channelKinds: ['underwater', 'water', 'marine'],
    icon: 'waves',
    accentClass: 'border-cyan-400 bg-cyan-50 text-cyan-950',
    expectedRange: '30 m clear water',
    detectorLabel: 'Threshold detector',
    realismLabel: 'Absorption-limited',
    defaultCurveRecipeId: 'gain-water-extinction',
    scenario: mediumScenarios.underwater,
  },
  custom: {
    id: 'custom',
    label: 'Custom scenario',
    shortLabel: 'Custom',
    summary: 'Starts from the designer default and leaves medium assumptions open for manual tuning.',
    channelKinds: [],
    icon: 'sliders',
    accentClass: 'border-slate-400 bg-slate-50 text-slate-900',
    expectedRange: 'User-defined',
    detectorLabel: 'User-defined',
    realismLabel: 'Manual',
    defaultCurveRecipeId: 'custom-axis',
    scenario: mediumScenarios.custom,
  },
}

export const mediumOptions = mediumIds.map((id) => mediumDefinitions[id])

export function scenarioForMedium(id: MediumId): ScenarioPayload {
  return cloneJson(mediumDefinitions[id].scenario)
}

export function inferMediumFromScenario(scenario: ScenarioPayload): MediumId {
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
    source?: Record<string, unknown>
    channel?: Record<string, unknown>
    detector?: Record<string, unknown>
    distanceScheduleValue?: number
  },
): ScenarioPayload {
  const scenario = cloneJson(defaultScenario)
  const next: ScenarioPayload = {
    ...scenario,
    metadata: {
      ...readRecord(scenario.metadata),
      mediumId,
    },
  }

  if (updates.pulses !== undefined) {
    next.pulses = updates.pulses
  }
  if (updates.source) {
    next.source = { ...readRecord(scenario.source), ...updates.source }
  }
  if (updates.channel) {
    next.channel = { ...readRecord(scenario.channel), ...updates.channel }
  }
  if (updates.detector) {
    next.detector = { ...readRecord(scenario.detector), ...updates.detector }
  }
  if (updates.distanceScheduleValue !== undefined) {
    next.dynamic = {
      ...readRecord(scenario.dynamic),
      parameter_schedules: [
        {
          target: 'channel.distance_km',
          profile: {
            kind: 'constant',
            start_s: 0,
            end_s: 0.001,
            value: updates.distanceScheduleValue,
          },
        },
      ],
    }
  }

  return next
}

function readRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {}
}

function isMediumId(value: unknown): value is MediumId {
  return typeof value === 'string' && mediumIds.includes(value as MediumId)
}
