import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import {
  cancelRun,
  createRun,
  estimateRun,
  fetchRunResult,
  fetchRunStatus,
  type JobStatus,
} from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'
import { useDesignerStore } from '@/features/designer/scenarioStore'

import { ExecutionView } from './ExecutionView'

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    cancelRun: vi.fn(),
    createRun: vi.fn(),
    estimateRun: vi.fn(),
    fetchRunResult: vi.fn(),
    fetchRunStatus: vi.fn(),
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  localStorage.clear()
  useDesignerStore.setState(useDesignerStore.getInitialState(), true)
})

test('aborts an in-flight status request when the view unmounts', async () => {
  vi.mocked(estimateRun).mockResolvedValue(createdRun().cost_estimate)
  vi.mocked(createRun).mockResolvedValue(createdRun())
  let observedSignal: AbortSignal | undefined
  vi.mocked(fetchRunStatus).mockImplementation(
    async (_jobId, signal) =>
      new Promise<JobStatus>((_resolve, reject) => {
        observedSignal = signal
        signal?.addEventListener('abort', () => reject(signal.reason), { once: true })
      }),
  )
  const view = renderExecution()

  fireEvent.click(screen.getByRole('button', { name: 'Ejecutar experimento' }))
  await waitFor(() => expect(fetchRunStatus).toHaveBeenCalledTimes(1))

  view.unmount()

  expect(observedSignal?.aborted).toBe(true)
})

test('continues monitoring after cancellation_requested and unlocks execution when cancelled', async () => {
  vi.mocked(estimateRun).mockResolvedValue(createdRun().cost_estimate)
  vi.mocked(createRun).mockResolvedValue(createdRun())
  vi.mocked(fetchRunStatus)
    .mockResolvedValueOnce(status('running'))
    .mockResolvedValueOnce(status('cancelled'))
  vi.mocked(cancelRun).mockResolvedValue({
    cancelled: false,
    cancellation_requested: true,
    status: 'cancellation_requested',
  })
  renderExecution()

  fireEvent.click(screen.getByRole('button', { name: 'Ejecutar experimento' }))
  await screen.findByText(/En ejecución/)
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))

  await screen.findByText(/Cancelación solicitada/)
  expect(cancelRun).toHaveBeenCalledWith('r_test')
  await waitFor(() => expect(fetchRunStatus).toHaveBeenCalledTimes(2))
  await waitFor(() => expect((screen.getByRole('button', { name: 'Ejecutar experimento' }) as HTMLButtonElement).disabled).toBe(false))
})

test('resumes monitoring when the cancellation request itself fails', async () => {
  vi.mocked(estimateRun).mockResolvedValue(createdRun().cost_estimate)
  vi.mocked(createRun).mockResolvedValue(createdRun())
  vi.mocked(fetchRunStatus)
    .mockResolvedValueOnce(status('running'))
    .mockResolvedValueOnce(status('cancelled'))
  vi.mocked(cancelRun).mockRejectedValue(new Error('No se pudo cancelar el run'))
  renderExecution()

  fireEvent.click(screen.getByRole('button', { name: 'Ejecutar experimento' }))
  await waitFor(() => expect(useDesignerStore.getState().activeRun?.status?.status).toBe('running'))
  const cancel = screen.getByRole('button', { name: 'Cancelar' }) as HTMLButtonElement
  await waitFor(() => expect(cancel.disabled).toBe(false))
  fireEvent.click(cancel)

  expect(await screen.findByText('No se pudo cancelar el run')).toBeTruthy()
  await waitFor(() => expect(fetchRunStatus).toHaveBeenCalledTimes(2))
  await waitFor(() => expect((screen.getByRole('button', { name: 'Ejecutar experimento' }) as HTMLButtonElement).disabled).toBe(false))
})

test('explains a validation block when the user asks to execute', async () => {
  renderExecution({ validationBlocked: true })

  expect(screen.queryByRole('alert')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Ejecutar experimento' }))

  expect((await screen.findByRole('alert')).textContent).toMatch(/No se puede ejecutar/)
  expect(createRun).not.toHaveBeenCalled()
})

test('hydrates a compact persisted run from its durable backend job reference', async () => {
  const created = createdRun()
  useDesignerStore.setState({
    runs: [{
      jobId: created.job_id,
      label: 'Persistido',
      digest: created.digest,
      scenario: structuredClone(defaultScenario),
      seed: defaultScenario.seed,
      startedAt: '2026-08-12T10:00:00Z',
      completedAt: '2026-08-12T10:00:01Z',
      status: status('done'),
      result: {},
      costEstimate: created.cost_estimate,
    }],
  })
  vi.mocked(fetchRunResult).mockResolvedValue({ metrics: { qber: 0.01 } })

  renderExecution()

  await waitFor(() => expect(fetchRunResult).toHaveBeenCalledWith('r_test', expect.any(AbortSignal)))
  await waitFor(() => expect(useDesignerStore.getState().runs[0]?.result).toEqual({ metrics: { qber: 0.01 } }))
})

function renderExecution({ validationBlocked = false }: { validationBlocked?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ExecutionView scenario={{ ...structuredClone(defaultScenario), pulses: 8 }} validationBlocked={validationBlocked} />
    </QueryClientProvider>,
  )
}

function createdRun() {
  return {
    job_id: 'r_test',
    status: 'queued' as const,
    digest: 'digest-test',
    cost_estimate: {
      estimate_kind: 'upper_bound' as const,
      evaluations: 1,
      pulses_per_evaluation: 8,
      total_pulse_events: 8,
      estimated_max_circuits: 8,
      shots_per_circuit: 1,
      estimated_max_shots: 8,
      estimated_stored_events: 0,
      backend: 'statevector' as const,
      full_event_log: false,
      warnings: [],
    },
  }
}

function status(value: JobStatus['status']): JobStatus {
  return {
    job_id: 'r_test',
    status: value,
    progress: { done: 1, total: 8 },
    elapsed_s: 0.1,
  }
}
