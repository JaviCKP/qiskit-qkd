import { expect, test } from 'vitest'

import type { CatalogField } from '@/api/client'
import { visibleFieldsForMedium } from './fieldVisibility'

const fields = [
  field('channel.kind'),
  field('channel.distance_km'),
  field('channel.attenuation_db_km'),
  field('channel.chromatic_dispersion_ps_nm_km'),
  field('channel.pmd_coefficient_ps_sqrt_km'),
  field('channel.pointing_jitter_rad'),
  field('channel.scintillation_sigma'),
  field('channel.underwater_extinction_m_inv'),
  field('channel.underwater_scattering_broadening_ns_per_m'),
  field('detector.efficiency'),
  field('timing.jitter_std_s'),
  field('source.mean_photon_number'),
  field('source.decoy_intensities', {
    visible_when: { target: 'source.kind', equals: 'decoy_weak_coherent' },
  }),
  field('e91.bell_state', {
    visible_when: { target: 'protocol.name', equals: 'e91' },
  }),
  field('e91.alice_angles_rad', {
    visible_when: { target: 'protocol.name', equals: 'e91' },
  }),
]

test('fiber shows fiber fields and hides air and underwater fields', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: { source: { kind: 'decoy_weak_coherent' } },
    expert: false,
    search: '',
  }).map((item) => item.key)

  expect(visible).toContain('channel.chromatic_dispersion_ps_nm_km')
  expect(visible).toContain('channel.pmd_coefficient_ps_sqrt_km')
  expect(visible).not.toContain('channel.pointing_jitter_rad')
  expect(visible).not.toContain('channel.underwater_extinction_m_inv')
})

test('ideal hides physical medium impairment fields', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'ideal',
    scenario: { source: { kind: 'ideal_single_photon' } },
    expert: false,
    search: '',
  }).map((item) => item.key)

  expect(visible).toContain('channel.kind')
  expect(visible).toContain('detector.efficiency')
  expect(visible).not.toContain('channel.attenuation_db_km')
  expect(visible).not.toContain('channel.pmd_coefficient_ps_sqrt_km')
  expect(visible).not.toContain('channel.scintillation_sigma')
  expect(visible).not.toContain('channel.underwater_extinction_m_inv')
})

test('custom shows all fields while expert mode still respects the active medium', () => {
  const custom = visibleFieldsForMedium({
    fields,
    mediumId: 'custom',
    scenario: { source: { kind: 'decoy_weak_coherent' } },
    expert: false,
    search: '',
  }).map((item) => item.key)
  const expert = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: { source: { kind: 'decoy_weak_coherent' } },
    expert: true,
    search: '',
  }).map((item) => item.key)

  expect(custom).toContain('channel.pointing_jitter_rad')
  expect(custom).toContain('channel.underwater_extinction_m_inv')
  expect(expert).not.toContain('channel.pointing_jitter_rad')
  expect(expert).not.toContain('channel.underwater_extinction_m_inv')
})

test('search never reveals fields from another medium', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: { source: { kind: 'ideal_single_photon' } },
    expert: false,
    search: 'pointing',
  }).map((item) => item.key)

  expect(visible).toEqual([])
})

test('search does not reveal catalog-hidden fields', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: { source: { kind: 'ideal_single_photon' } },
    expert: false,
    search: 'decoy',
  }).map((item) => item.key)

  expect(visible).toEqual([])
})

test('hides scalar source intensity when named decoys take precedence', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: {
      source: {
        kind: 'decoy_weak_coherent',
        decoy_intensities: [{ name: 'signal' }],
      },
    },
    expert: true,
    search: '',
  }).map((item) => item.key)

  expect(visible).toContain('source.decoy_intensities')
  expect(visible).not.toContain('source.mean_photon_number')
})

test('e91 fields are visible when protocol enables them', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: {
      protocol: { name: 'e91' },
      source: { kind: 'ideal_single_photon' },
    },
    expert: false,
    search: '',
  }).map((item) => item.key)

  expect(visible).toContain('e91.bell_state')
  expect(visible).toContain('e91.alice_angles_rad')
})

test('published channel applicability hides scientifically irrelevant fields', () => {
  const visible = visibleFieldsForMedium({
    fields: [field('channel.attenuation_db_km', { applicable_channel_kinds: ['fiber'] })],
    mediumId: 'air',
    scenario: { channel: { kind: 'free_space' } },
    expert: true,
    search: '',
  })
  expect(visible).toEqual([])
})

function field(key: string, overrides: Partial<CatalogField> = {}): CatalogField {
  return {
    key,
    label_es: key,
    type: 'number',
    unit: null,
    default: 0,
    sweepable: true,
    ...overrides,
  }
}
