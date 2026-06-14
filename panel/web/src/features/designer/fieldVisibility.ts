import type { CatalogField } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'
import { readTarget } from '@/features/shared/scenarioPaths'

type VisibleFieldsArgs = {
  fields: CatalogField[]
  mediumId: MediumId
  scenario: Record<string, unknown>
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
  'source.kind',
  'source.emission_probability',
  'source.mean_photon_number',
  'source.preparation_error_probability',
  'source.decoy_intensities',
  'channel.kind',
  'channel.distance_km',
  'channel.depolarizing_probability',
  'channel.phase_damping_probability',
  'detector.kind',
  'detector.efficiency',
  'detector.dark_count_rate_hz',
  'detector.gate_width_s',
  'detector.readout_error_probability',
  'timing.propagation_delay_s',
  'timing.jitter_std_s',
  'timing.clock_offset_s',
  'timing.clock_drift_ppm',
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
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.background_count_rate_hz',
  ]),
  air: new Set([
    ...baseFields,
    'channel.wavelength_nm',
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
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.atmospheric_extinction_db_km',
    'channel.scintillation_sigma',
    'channel.pointing_jitter_rad',
    'channel.background_count_rate_hz',
  ]),
  underwater: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.underwater_extinction_m_inv',
    'channel.underwater_scattering_broadening_ns_per_m',
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
    if (!isCatalogVisible(field, scenario) && query.length === 0) {
      return false
    }
    if (query.length > 0) {
      return matchesSearch(field, query)
    }
    if (expert || mediumId === 'custom') {
      return true
    }
    const allowed = mediumFields[mediumId]
    return allowed === null || allowed.has(field.key)
  })
}

export function isCatalogVisible(
  field: CatalogField,
  scenario: Record<string, unknown>,
): boolean {
  if (!field.visible_when) {
    return true
  }
  return readTarget(scenario, field.visible_when.target) === field.visible_when.equals
}

function matchesSearch(field: CatalogField, query: string): boolean {
  return (
    field.key.toLowerCase().includes(query) ||
    field.label_es.toLowerCase().includes(query)
  )
}
