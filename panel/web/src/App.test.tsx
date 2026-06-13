import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

vi.mock('plotly.js-dist-min', () => ({
  default: { react: vi.fn(), purge: vi.fn(), Plots: { resize: vi.fn() } },
}))

vi.mock('react-plotly.js/factory', () => ({
  default: () => () => <div>Timeline Plotly</div>,
}))

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows the designer generated from catalog and live API state', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/health') {
        return jsonResponse({ status: 'ok', service: 'qiskit-qkd-panel' })
      }
      if (url === '/api/catalog') {
        return jsonResponse({
          sections: [
            {
              key: 'channel',
              label_es: 'Canal',
              fields: [
                {
                  key: 'channel.kind',
                  label_es: 'Familia',
                  type: 'select',
                  unit: null,
                  default: 'fiber',
                  sweepable: false,
                },
                {
                  key: 'channel.distance_km',
                  label_es: 'Distancia',
                  type: 'number',
                  unit: 'km',
                  default: 0,
                  sweepable: true,
                },
              ],
            },
          ],
          metrics: [{ key: 'qber', label_es: 'qber', unit: null }],
        })
      }
      if (url === '/api/scenarios/validate') {
        return jsonResponse({ valid: true, digest: 'abcd1234ef' })
      }
      if (url === '/api/characterize/channel') {
        return jsonResponse({
          section: 'channel',
          state: {
            loss_db: 3.2,
            transmittance: 0.48,
          },
        })
      }
      if (url === '/api/characterize/source') {
        return jsonResponse({
          section: 'source',
          state: { mean_photon_rate_hz: 1000 },
        })
      }
      if (url === '/api/characterize/detector') {
        return jsonResponse({
          section: 'detector',
          state: { p_dark_per_gate: 0.000001 },
        })
      }
      if (url === '/api/characterize/timing') {
        return jsonResponse({
          section: 'timing',
          state: { effective_jitter_std_s: 0 },
        })
      }
      if (url === '/api/dynamics/preview') {
        return jsonResponse({ rows: [{ time_s: 0, 'channel.distance_km': 0 }] })
      }
      throw new Error(`Unexpected URL: ${url}`)
    }),
  )

  render(<App />)

  expect(await screen.findByText('API ok')).toBeTruthy()
  expect(screen.getByText('qiskit-qkd-panel')).toBeTruthy()
  expect((await screen.findAllByText('Diseñador')).length).toBeGreaterThan(0)
  expect((await screen.findAllByText('channel.distance_km')).length).toBeGreaterThan(0)
  expect(await screen.findByText('Digest abcd1234')).toBeTruthy()
  expect(await screen.findByText('3.20 dB')).toBeTruthy()
  expect(await screen.findByText('Timeline Plotly')).toBeTruthy()
})

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response
}
