import type { CatalogField, JsonObject } from '@/api/client'
import { mediumDefinitions, type MediumId } from '@/features/lab/mediums'
import { readTarget } from '@/features/shared/scenarioPaths'

type VisibleFieldsArgs = {
  fields: CatalogField[]
  mediumId: MediumId
  scenario: JsonObject
  expert: boolean
  search: string
}

const baseFields = new Set([
  'scenario.pulses',
  'scenario.clock_rate_hz',
  'scenario.seed',
  'scenario.event_sample_size',
  'protocol.name',
  'protocol.basis_choices',
  'e91.bell_state',
  'e91.alice_angles_rad',
  'e91.bob_angles_rad',
  'e91.key_setting_pairs',
  'e91.chsh_terms',
  'e91.bob_key_bit_flip',
  'e91.chsh_estimation_enabled',
  'source.kind',
  'source.emission_probability',
  'source.mean_photon_number',
  'source.preparation_error_probability',
  'source.decoy_intensities',
  'channel.kind',
  'channel.distance_km',
  'channel.depolarizing_probability',
  'channel.phase_damping_probability',
  'channel.polarization_rotation_y_rad',
  'channel.polarization_rotation_z_rad',
  'detector.kind',
  'detector.efficiency',
  'detector.dark_count_rate_hz',
  'detector.gate_width_s',
  'detector.readout_error_probability',
  'detector.double_click_policy',
  'timing.propagation_delay_s',
  'timing.jitter_std_s',
  'timing.clock_offset_s',
  'timing.clock_drift_ppm',
  'timing.slot_assignment_policy',
  'post_processing.sifting_enabled',
  'post_processing.qber_abort_threshold',
  'post_processing.qber_sample_fraction',
  'post_processing.error_correction_efficiency',
  'post_processing.reconciliation_block_size',
  'post_processing.privacy_amplification_enabled',
  'post_processing.decoy_security_estimation_enabled',
  'post_processing.decoy_security_method',
  'eavesdropper.kind',
  'eavesdropper.intercept_probability',
  'eavesdropper.pns_split_probability',
  'eavesdropper.pns_block_single_photon_probability',
])

const mediumFields: Record<MediumId, Set<string> | null> = {
  ideal: new Set([
    ...baseFields,
    'detector.double_click_policy',
  ]),
  fiber: new Set([
    ...baseFields,
    'channel.attenuation_db_km',
    'channel.fixed_loss_db',
    'channel.background_count_rate_hz',
    'channel.wavelength_nm',
    'channel.pmd_coefficient_ps_sqrt_km',
    'channel.chromatic_dispersion_ps_nm_km',
    'channel.source_spectral_width_nm',
    'channel.polarization_dependent_loss_db',
    'channel.pdl_axis_basis',
    'channel.pdl_axis_bit',
    'channel.classical_channel_power_mw',
    'channel.raman_coefficient_hz_mw_km',
    'channel.raman_filter_isolation_db',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
    'detector.double_click_policy',
  ]),
  vacuum: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.fixed_loss_db',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.background_count_rate_hz',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
  ]),
  air: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.fixed_loss_db',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.atmospheric_extinction_db_km',
    'channel.scintillation_sigma',
    'channel.pointing_jitter_rad',
    'channel.background_count_rate_hz',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
  ]),
  satellite: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.fixed_loss_db',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.atmospheric_extinction_db_km',
    'channel.scintillation_sigma',
    'channel.pointing_jitter_rad',
    'channel.background_count_rate_hz',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
  ]),
  underwater: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.fixed_loss_db',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.underwater_extinction_m_inv',
    'channel.underwater_scattering_broadening_ns_per_m',
    'channel.scintillation_sigma',
    'channel.pointing_jitter_rad',
    'channel.background_count_rate_hz',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
  ]),
  custom: null,
}

export function visibleFieldsForMedium({
  fields,
  mediumId,
  scenario,
  expert,
  search,
}: VisibleFieldsArgs): CatalogField[] {
  const query = search.trim().toLowerCase()
  return fields.filter((field) => {
    const catalogVisible = isCatalogVisible(field, scenario)
    if (!catalogVisible) {
      return false
    }
    const allowed = mediumFields[mediumId]
    const publishedKinds = field.applicable_channel_kinds
    if (publishedKinds?.length) {
      const mediumKinds = mediumDefinitions[mediumId].channelKinds
      if (mediumId !== 'custom' && !publishedKinds.some((kind) => mediumKinds.includes(kind))) {
        return false
      }
    } else if (allowed !== null && !allowed.has(field.key)) {
      // Legacy/offline catalog fallback.  Published fields with explicit
      // applicability above never consult this hand-maintained visual list.
      return false
    }
    if (query.length > 0) {
      return matchesSearch(field, query)
    }
    if (expert || mediumId === 'custom') {
      return true
    }
    return true
  })
}

export function isCatalogVisible(
  field: CatalogField,
  scenario: JsonObject,
): boolean {
  if (field.effect_status === 'ignored' || field.effect_status === 'unsupported') {
    return false
  }
  if (!field.visible_when) {
    return capabilityApplies(field, scenario) && !isShadowed(field, scenario)
  }
  return (
    readTarget(scenario, field.visible_when.target) === field.visible_when.equals &&
    capabilityApplies(field, scenario) &&
    !isShadowed(field, scenario)
  )
}

function capabilityApplies(field: CatalogField, scenario: JsonObject): boolean {
  return (
    includes(field.applicable_protocols, readTarget(scenario, 'protocol.name')) &&
    includes(field.applicable_source_kinds, readTarget(scenario, 'source.kind')) &&
    includes(field.applicable_channel_kinds, readTarget(scenario, 'channel.kind')) &&
    includes(field.applicable_detector_kinds, readTarget(scenario, 'detector.kind'))
  )
}

function isShadowed(field: CatalogField, scenario: JsonObject): boolean {
  if (field.key !== 'source.mean_photon_number') return false
  const intensities = readTarget(scenario, 'source.decoy_intensities')
  return Array.isArray(intensities) && intensities.length > 0
}

function includes(allowed: string[] | undefined, value: unknown): boolean {
  return !allowed?.length || (typeof value === 'string' && allowed.includes(value))
}

function matchesSearch(field: CatalogField, query: string): boolean {
  return (
    field.key.toLowerCase().includes(query) ||
    field.label_es.toLowerCase().includes(query)
  )
}
