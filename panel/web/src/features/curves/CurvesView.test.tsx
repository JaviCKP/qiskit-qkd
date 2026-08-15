import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'

import type { JsonObject } from '@/api/client'

import { AccessibleCurveTable } from './CurvesView'

afterEach(() => {
  document.body.innerHTML = ''
})

test('limits a 4096-row accessible table to 256 rows per page', () => {
  const rows = Array.from({ length: 4_096 }, (_, index) => ({ axis: index, metric: index / 10 })) as JsonObject[]
  render(<AccessibleCurveTable axisKey="axis" metricKey="metric" rows={rows} seriesKey="" />)

  fireEvent.click(screen.getByText(/4096 filas/))
  expect(screen.getAllByRole('row')).toHaveLength(257)
  expect(screen.getByText('Mostrando 1-256 de 4096')).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  expect(screen.getByText('Mostrando 257-512 de 4096')).toBeTruthy()
  expect(screen.getAllByRole('row')).toHaveLength(257)
})
