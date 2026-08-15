import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import type { CatalogSection } from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'

import { PhysicalFlowBuilder } from './PhysicalFlowBuilder'

afterEach(cleanup)

test('explains and exposes decoy intensities when ideal emission probability does not apply', () => {
  const scenario = structuredClone(defaultScenario)
  scenario.channel.kind = 'free_space'
  scenario.source.kind = 'decoy_weak_coherent'
  const sections: CatalogSection[] = [{
    key: 'source',
    label_es: 'Fuente',
    fields: [
      field('source.kind', 'Tipo de fuente', 'select', scenario.source.kind),
      field('source.emission_probability', 'Probabilidad de emisión', 'number', 1, ['ideal_single_photon']),
      field('source.mean_photon_number', 'Fotones medios', 'number', null, ['weak_coherent']),
      field('source.decoy_intensities', 'Intensidades decoy', 'decoy_table', scenario.source.decoy_intensities, ['decoy_weak_coherent']),
    ],
  }]

  render(
    <PhysicalFlowBuilder
      editedFields={[]}
      errors={[]}
      mediumId="air"
      onChange={vi.fn()}
      onSelectMedium={vi.fn()}
      scenario={scenario}
      sections={sections}
    />,
  )

  expect(screen.queryByLabelText('Probabilidad de emisión')).toBeNull()
  expect(screen.getByText('La emisión se controla con intensidades μ')).toBeTruthy()
  expect(screen.getByText(/por eso la probabilidad de emisión ideal no se aplica/)).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: /Editar intensidades y probabilidades/ }))
  expect(screen.getByRole('dialog', { name: 'Ajustes avanzados de Emisor' })).toBeTruthy()
  expect(screen.getByText('Intensidades de señal y decoy')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Información sobre Intensidades de señal y decoy' })).toBeTruthy()
})

function field(key: string, label_es: string, type: string, defaultValue: unknown, applicableSourceKinds?: string[]) {
  return {
    key,
    label_es,
    type,
    unit: null,
    default: defaultValue,
    sweepable: true,
    applicable_source_kinds: applicableSourceKinds,
  }
}
