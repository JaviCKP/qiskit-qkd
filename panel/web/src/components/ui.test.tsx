import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, expect, test } from 'vitest'

import { Dialog, StatusBadge, ValidationSummary } from './ui'

afterEach(cleanup)

test('traps dialog focus, closes with Escape, and restores the trigger', async () => {
  function Harness() {
    const [open, setOpen] = useState(false)
    return (
      <>
        <button onClick={() => setOpen(true)} type="button">Abrir ajustes</button>
        <Dialog onClose={() => setOpen(false)} open={open} title="Ajustes">
          <button type="button">Primer control</button>
        </Dialog>
      </>
    )
  }

  render(<Harness />)
  const trigger = screen.getByRole('button', { name: 'Abrir ajustes' })
  trigger.focus()
  fireEvent.click(trigger)
  const close = screen.getByRole('button', { name: 'Cerrar Ajustes' })
  const first = screen.getByRole('button', { name: 'Primer control' })
  expect(document.activeElement).toBe(close)
  expect(trigger.getAttribute('inert')).toBe('')
  expect(trigger.getAttribute('aria-hidden')).toBe('true')

  fireEvent.keyDown(document, { key: 'Tab' })
  expect(document.activeElement).toBe(first)
  fireEvent.keyDown(document, { key: 'Tab' })
  expect(document.activeElement).toBe(close)
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(screen.queryByRole('dialog', { name: 'Ajustes' })).toBeNull()
  await waitFor(() => expect(document.activeElement).toBe(trigger))
  expect(trigger.hasAttribute('inert')).toBe(false)
  expect(trigger.hasAttribute('aria-hidden')).toBe(false)
})

const availableAssessment = {
  protocol: 'bb84',
  data_status: 'available',
  qber_defined: true,
  qber_value: 0.02,
  sample_size: 128,
  security_scope: 'pedagogical_asymptotic_diagnostic',
} as const

test.each([
  [
    {
      ...availableAssessment,
      data_status: 'insufficient_data',
      qber_defined: false,
      qber_value: null,
      sample_size: 0,
      key_status: 'no_key_insufficient_data',
    },
    'SIN MUESTRA',
  ],
  [{ ...availableAssessment, key_status: 'no_key_threshold_exceeded' }, 'ABORTADO POR UMBRAL'],
  [{ ...availableAssessment, key_status: 'no_key_verification_failed' }, 'CLAVE DESCARTADA'],
  [{ ...availableAssessment, key_status: 'estimated_key_available' }, 'CLAVE ESTIMADA'],
  [{ ...availableAssessment, key_status: 'no_extractable_key' }, 'SIN CLAVE ESTIMADA'],
  [{ ...availableAssessment, key_status: 'unknown' }, 'RESULTADO DIAGNÓSTICO'],
])('renders assessment key status as %s', (assessment, expectedLabel) => {
  render(
    <StatusBadge
      summary={{
        assessment,
        metrics: { abort: false, qber: 0, secure: true, sifted: 0 },
      }}
    />,
  )

  expect(screen.getByText(expectedLabel)).toBeTruthy()
  expect(screen.queryByText('SEGURO')).toBeNull()
})

test('treats a legacy zero-sample result conservatively', () => {
  render(
    <StatusBadge
      summary={{
        metrics: {
          abort: false,
          detected: 0,
          qber: 0,
          secret_key_rate_bps: 0,
          secure: true,
          sifted: 0,
        },
        classical: { final_key_length: 0, verification_passed: true },
      }}
    />,
  )

  expect(screen.getByText('SIN MUESTRA')).toBeTruthy()
  expect(screen.queryByText('SEGURO')).toBeNull()
})

test('accepts metrics and assessment as additive explicit props', () => {
  render(
    <StatusBadge
      assessment={{
        ...availableAssessment,
        key_status: 'no_extractable_key',
      }}
      metrics={{ abort: false, secret_key_rate_bps: 50, secure: true, sifted: 128 }}
    />,
  )

  expect(screen.getByText('SIN CLAVE ESTIMADA')).toBeTruthy()
  expect(screen.queryByText('SEGURO')).toBeNull()
})

test('localizes common API validation messages without hiding the technical location', () => {
  render(
    <ValidationSummary
      issues={[{ loc: 'scenario.pulses', msg: 'pulses must be greater than 0', severity: 'error' }]}
    />,
  )

  expect(screen.getByText('scenario.pulses')).toBeTruthy()
  expect(screen.getByText(/El valor debe ser mayor que 0/)).toBeTruthy()
  expect(screen.queryByText(/must be greater/)).toBeNull()
})
