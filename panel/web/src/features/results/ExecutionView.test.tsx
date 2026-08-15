import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import type { JobStatus, JsonObject } from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'

import { ResultDetails, type RunSnapshot } from './ExecutionView'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function snapshot(assessment: JsonObject, result: JsonObject = {}): RunSnapshot {
  const status: JobStatus = {
    job_id: 'job-test',
    status: 'done',
    progress: { done: 1, total: 1 },
    elapsed_s: 0.1,
    result_summary: { assessment, metrics: { qber: 0, secure: true, sifted: 0 } },
  }
  return {
    jobId: status.job_id,
    label: 'Run de prueba',
    digest: '1234567890abcdef',
    scenario: structuredClone(defaultScenario),
    seed: defaultScenario.seed,
    startedAt: '2026-08-09T10:00:00Z',
    completedAt: '2026-08-09T10:00:01Z',
    result,
    status,
    costEstimate: costEstimate(),
  }
}

test('renders zero-sample QBER and key rate without an optimistic security claim', () => {
  render(
    <ResultDetails
      latestRun={snapshot({
        assumptions: ['Canal estacionario durante cada pulso.'],
        data_status: 'insufficient_data',
        key_status: 'no_key_insufficient_data',
        qber_defined: false,
        qber_value: null,
        rate_estimate_bps: null,
        reasons: ['No hubo bits cribados observables.'],
        sample_size: 0,
        security_scope: 'pedagogical_asymptotic_diagnostic',
      })}
      previousRun={null}
    />,
  )

  expect(screen.getByText('SIN MUESTRA')).toBeTruthy()
  expect(screen.getAllByText('QBER').length).toBeGreaterThan(0)
  expect(screen.getByText('No definido (n=0)')).toBeTruthy()
  expect(screen.getAllByText('Tasa secreta estimada').length).toBeGreaterThan(0)
  expect(screen.getAllByText('No disponible').length).toBeGreaterThan(0)
  expect(screen.getByText(/Estimación pedagógica y asintótica/)).toBeTruthy()
  expect(screen.getAllByText(/No hubo bits cribados observables/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/Canal estacionario durante cada pulso/).length).toBeGreaterThan(0)
  expect(screen.queryByText('SEGURO')).toBeNull()
  expect(screen.queryByText(/"secure"/)).toBeNull()
})

test('labels a legacy CHSH sample size as unavailable rather than zero', () => {
  const status: JobStatus = {
    job_id: 'job-legacy-chsh',
    status: 'done',
    progress: { done: 1, total: 1 },
    elapsed_s: 0.1,
    result_summary: { metrics: { chsh_s: 2.5, qber: 0.02, sifted: 128 } },
  }

  render(
    <ResultDetails
      latestRun={{ ...snapshot({}), digest: 'legacy-chsh', jobId: status.job_id, status }}
      previousRun={null}
    />,
  )

  expect(screen.getByText('2.50 (n no disponible)')).toBeTruthy()
})

test('labels E91 as an observed CHSH diagnostic with sample and limited conclusion', () => {
  render(
    <ResultDetails
      latestRun={snapshot(
        {
          chsh_sample_size: 400,
          chsh_sample_size_by_term: { a0b0: 100, a0b1: 100, a1b0: 100, a1b1: 100 },
          conclusion_scope: 'diagnostic_fair_sampling_no_significance_test',
          data_status: 'available',
          key_status: 'unknown',
          observed_chsh_s: 2.5,
          observed_threshold_exceeded: true,
          qber_defined: true,
          qber_value: 0.02,
          sample_size: 128,
          security_scope: 'pedagogical_asymptotic_diagnostic',
        },
        { bell: { observed_chsh_s: 2.5 } },
      )}
      previousRun={null}
    />,
  )

  expect(screen.getByText('CHSH observado')).toBeTruthy()
  expect(screen.getByText('2.50 (n=400)')).toBeTruthy()
  expect(screen.getByText(/supera el umbral CHSH de referencia/)).toBeTruthy()
  expect(screen.getByText(/sin prueba de significación estadística/)).toBeTruthy()
})

test('explores and downloads the retained event sample', () => {
  const createObjectURL = vi.fn(() => 'blob:qkd-events')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  const latestRun = snapshot(
    {
      data_status: 'available',
      key_status: 'estimated_key_available',
      qber_defined: true,
      qber_value: 0.01,
      sample_size: 1,
    },
    { event_sample: [{ index: 1, timing_status: 'ok', detected: true }] },
  )
  latestRun.scenario.store_full_event_log = true

  render(<ResultDetails latestRun={latestRun} previousRun={null} />)

  fireEvent.click(screen.getByRole('tab', { name: 'Eventos' }))
  expect(screen.getByText('1 eventos conservados')).toBeTruthy()
  expect(screen.getByText('Este run guardó el registro completo.')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /CSV/ }))
  expect(createObjectURL).toHaveBeenCalledTimes(1)
})

test('explains a failed reconciliation and renders classical and provenance data without raw JSON', () => {
  const latestRun = snapshot(
    {
      data_status: 'available',
      key_status: 'no_key_verification_failed',
      qber_defined: true,
      qber_value: 11 / 656,
      rate_estimate_bps: 494769.667,
      rate_estimate_status: 'inconsistent_with_key_status',
      sample_size: 656,
      security_scope: 'pedagogical_asymptotic_diagnostic',
    },
    {
      classical: {
        ambiguous_blocks: 1,
        blocks_corrected: 9,
        candidate_key_length: 656,
        final_key_length: 0,
        leak_ec_bits: 109,
        qber_abort_threshold: 0.11,
        qber_sample_size: 656,
        residual_mismatches: 2,
        threshold_exceeded: false,
        verification_passed: false,
        verification_status: 'failed',
      },
      provenance: {
        backend: 'statevector',
        primitive: 'SamplerV2',
        scenario_digest: '1234567890abcdef',
        qiskit_version: '2.1.0',
        verification_status: 'unverified_import',
      },
    },
  )
  latestRun.status.result_summary = {
    assessment: latestRun.status.result_summary?.assessment,
    metrics: {
      detected: 1315,
      errors: 11,
      qber: 11 / 656,
      secret_key_rate_bps: 494769.667,
      sifted: 656,
    },
  }

  render(<ResultDetails latestRun={latestRun} previousRun={null} />)

  expect(screen.getByText('CLAVE DESCARTADA')).toBeTruthy()
  expect(screen.getByText(/Había 11 diferencias; se aplicó una corrección en 9 bloques/)).toBeTruthy()
  expect(screen.getByText(/quedaron 2 bits distintos en 1 bloque ambiguo/)).toBeTruthy()

  fireEvent.click(screen.getByRole('tab', { name: 'Clásico' }))
  expect(screen.getByRole('heading', { name: 'Reconciliación de Alice y Bob' })).toBeTruthy()
  expect(screen.getByText('2 discrepancias residuales')).toBeTruthy()
  expect(screen.queryByText(/"residual_mismatches"/)).toBeNull()

  fireEvent.click(screen.getByRole('tab', { name: 'Procedencia' }))
  expect(screen.getByText('Motor de simulación')).toBeTruthy()
  expect(screen.getByText('SamplerV2')).toBeTruthy()
  expect(screen.getByText(/Procedencia importada sin verificar/)).toBeTruthy()
  expect(screen.queryByText(/"backend"/)).toBeNull()
})

test('renders the decoy breakdown as a readable security summary and table', () => {
  const latestRun = snapshot(
    {
      data_status: 'available',
      key_status: 'estimated_key_available',
      qber_defined: true,
      qber_value: 0.01,
      sample_size: 597,
    },
    {
      decoy: {
        signal: { detected: 1191, gain: 0.1577, mean_photon_number: 0.6, pulses: 7552, qber: 0.0067, selection_fraction: 0.7552, sifted: 597 },
        vacuum: { detected: 4, gain: 0.0069, mean_photon_number: 0, pulses: 576, qber: 0.5, selection_fraction: 0.0576, sifted: 4 },
        security: { method: 'vacuum_weak_asymptotic', secret_key_rate_bps: 217389.16, single_photon_error_rate_upper_bound: 0.0604, single_photon_yield_lower_bound: 0.3014 },
      },
    },
  )

  render(<ResultDetails latestRun={latestRun} previousRun={null} />)
  fireEvent.click(screen.getByRole('tab', { name: 'Decoy' }))

  expect(screen.getByRole('heading', { name: 'Estimación con estados decoy' })).toBeTruthy()
  expect(screen.getByText('Tasa decoy estimada')).toBeTruthy()
  expect(screen.getByRole('columnheader', { name: 'Intensidad' })).toBeTruthy()
  expect(screen.getByText('Señal')).toBeTruthy()
  expect(screen.getByText('Vacío')).toBeTruthy()
  expect(screen.queryByText(/"mean_photon_number"/)).toBeNull()
})

function costEstimate() {
  return {
    estimate_kind: 'upper_bound' as const,
    evaluations: 1,
    pulses_per_evaluation: 1024,
    total_pulse_events: 1024,
    estimated_max_circuits: 1024,
    shots_per_circuit: 1,
    estimated_max_shots: 1024,
    estimated_stored_events: 0,
    backend: 'statevector' as const,
    full_event_log: false,
    warnings: [],
  }
}
