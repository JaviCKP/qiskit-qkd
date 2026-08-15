import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useMemo, useState } from 'react'
import { afterEach, expect, test } from 'vitest'

import { CurvePlot, type CurvePlotTrace } from './plot'

afterEach(cleanup)

test('renders labelled axes, gaps, threshold and accessible hover titles', () => {
  const traces: CurvePlotTrace[] = [
    { name: 'QBER', x: [0, 1, 2], y: [0.01, null, 0.03], line: { color: '#22d3ee' }, marker: { size: 6 } },
    { name: 'Tasa', x: [0, 1], y: [100, 125], line: { color: '#34d399' } },
  ]

  render(<CurvePlot traces={traces} title="Curva QKD" xLabel="Distancia" yLabel="QBER" threshold={0.11} thresholdLabel="Abortar" />)

  expect(screen.getByRole('img', { name: 'Curva QKD' })).toBeTruthy()
  expect(screen.getByText('Distancia')).toBeTruthy()
  expect(screen.getByText('QBER', { selector: 'text' })).toBeTruthy()
  expect(screen.getByText('Abortar')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'QBER' }).getAttribute('aria-pressed')).toBe('true')
  expect(screen.getAllByRole('img')[0]?.querySelectorAll('circle')).toHaveLength(4)
  expect(screen.getByRole('img', { name: 'Curva QKD' }).querySelector('circle title')?.textContent).toBe('QBER: 0, 0,01')
})

test('keeps chart DOM stable when polling progress changes with stable traces', () => {
  function Harness() {
    const [progress, setProgress] = useState(0)
    const traces = useMemo<CurvePlotTrace[]>(() => [{ name: 'serie', x: [0, 1], y: [0, 1] }], [])
    return <>
      <CurvePlot traces={traces} title="Curva" xLabel="X" yLabel="Y" />
      <button onClick={() => setProgress((value) => value + 1)} type="button">Progreso {progress}</button>
    </>
  }

  render(<Harness />)
  const chart = screen.getByRole('img', { name: 'Curva' })
  const path = chart.querySelector('path')
  fireEvent.click(screen.getByRole('button', { name: 'Progreso 0' }))
  expect(screen.getByRole('button', { name: 'Progreso 1' })).toBeTruthy()
  expect(screen.getByRole('img', { name: 'Curva' })).toBe(chart)
  expect(chart.querySelector('path')).toBe(path)
})

test('draws confidence bands without joining across missing values', () => {
  render(<CurvePlot
    traces={[
      { name: 'QBER p95', x: [0, 1, 2, 3], y: [0.3, 0.4, null, 0.5], line: { color: 'transparent' }, showlegend: false },
      { name: 'QBER p05', x: [0, 1, 2, 3], y: [0.1, 0.2, null, 0.25], fill: 'tonexty', fillcolor: '#22d3ee33', line: { color: 'transparent' }, showlegend: false },
      { name: 'QBER', x: [0, 1, 2, 3], y: [0.2, 0.3, null, 0.4], mode: 'lines+markers', line: { color: '#22d3ee' } },
    ]}
    title="Intervalo"
    xLabel="Distancia"
    yLabel="QBER"
  />)

  const chart = screen.getByRole('img', { name: 'Intervalo' })
  expect(chart.querySelectorAll('path[fill="#22d3ee33"]')).toHaveLength(1)
  expect(chart.querySelector('path[fill="#22d3ee33"]')?.getAttribute('d')).not.toContain('NaN')
  fireEvent.click(screen.getByRole('button', { name: 'QBER' }))
  expect(chart.querySelectorAll('path[fill="#22d3ee33"]')).toHaveLength(0)
})
