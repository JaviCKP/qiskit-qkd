import { describe, expect, test } from 'vitest'

import { fieldHelp, FIELD_HELP_ES } from './fieldHelp'

const catalogFieldKeys = [
  'channel.atmospheric_extinction_db_km',
  'channel.attenuation_db_km',
  'channel.background_count_rate_hz',
  'channel.beam_divergence_rad',
  'channel.chromatic_dispersion_ps_nm_km',
  'channel.classical_channel_power_mw',
  'channel.depolarizing_probability',
  'channel.distance_km',
  'channel.fixed_loss_db',
  'channel.kind',
  'channel.pdl_axis_basis',
  'channel.pdl_axis_bit',
  'channel.phase_damping_probability',
  'channel.pmd_coefficient_ps_sqrt_km',
  'channel.pointing_jitter_rad',
  'channel.polarization_dependent_loss_db',
  'channel.polarization_rotation_y_rad',
  'channel.polarization_rotation_z_rad',
  'channel.raman_coefficient_hz_mw_km',
  'channel.raman_filter_isolation_db',
  'channel.receiver_aperture_m',
  'channel.scintillation_sigma',
  'channel.source_spectral_width_nm',
  'channel.transmitter_aperture_m',
  'channel.underwater_extinction_m_inv',
  'channel.underwater_scattering_broadening_ns_per_m',
  'channel.wavelength_nm',
  'detector.afterpulse_probability',
  'detector.dark_count_rate_hz',
  'detector.dead_time_s',
  'detector.double_click_policy',
  'detector.efficiency',
  'detector.gate_width_s',
  'detector.kind',
  'detector.readout_error_probability',
  'dynamic.parameter_schedules',
  'e91.alice_angles_rad',
  'e91.bell_state',
  'e91.bob_angles_rad',
  'e91.bob_key_bit_flip',
  'e91.chsh_estimation_enabled',
  'e91.chsh_terms',
  'e91.key_setting_pairs',
  'eavesdropper.intercept_probability',
  'eavesdropper.kind',
  'eavesdropper.pns_block_single_photon_probability',
  'eavesdropper.pns_split_probability',
  'post_processing.decoy_security_estimation_enabled',
  'post_processing.decoy_security_method',
  'post_processing.error_correction_efficiency',
  'post_processing.privacy_amplification_enabled',
  'post_processing.qber_abort_threshold',
  'post_processing.qber_sample_fraction',
  'post_processing.reconciliation_block_size',
  'post_processing.sifting_enabled',
  'protocol.basis_choices',
  'protocol.name',
  'scenario.clock_rate_hz',
  'scenario.event_sample_size',
  'scenario.pulses',
  'scenario.seed',
  'scenario.store_full_event_log',
  'source.decoy_intensities',
  'source.emission_probability',
  'source.kind',
  'source.mean_photon_number',
  'source.preparation_error_probability',
  'timing.clock_drift_ppm',
  'timing.clock_offset_s',
  'timing.jitter_std_s',
  'timing.propagation_delay_s',
  'timing.slot_assignment_policy',
] as const

describe('fieldHelp', () => {
  test('has a specific one-sentence explanation for every catalog field', () => {
    expect(Object.keys(FIELD_HELP_ES).sort()).toEqual([...catalogFieldKeys].sort())
    for (const key of catalogFieldKeys) {
      const help = fieldHelp(key)
      expect(help).not.toMatch(/ajuste avanzado|modelo seleccionado/i)
      expect(help.length).toBeGreaterThan(20)
      expect(help).toMatch(/[.!?]$/)
    }
  })
})
