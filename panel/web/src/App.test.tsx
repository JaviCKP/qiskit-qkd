import { render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import App from './App'

afterEach(() => {
  vi.unstubAllGlobals()
})

test('shows the API health status from the backend', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ok', service: 'qiskit-qkd-panel' }),
    })),
  )

  render(<App />)

  expect(await screen.findByText('API ok')).toBeTruthy()
  expect(screen.getByText('qiskit-qkd-panel')).toBeTruthy()
})
