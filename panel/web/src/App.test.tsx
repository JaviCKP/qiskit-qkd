import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import type {
  CostEstimate,
  Experiment,
  JsonObject,
  ScenarioPayload,
  SweepCostEstimate,
} from '@/api/client'
import { queryClient } from '@/app/queryClient'
import { useDesignerStore } from '@/features/designer/scenarioStore'

import App from './App'

beforeEach(() => {
  localStorage.clear()
  queryClient.clear()
  useDesignerStore.setState(useDesignerStore.getInitialState(), true)
})

afterEach(() => {
  cleanup()
  queryClient.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('loads the compact medium-first scientific workbench with one inspection request', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)

  expect(await screen.findByText('QKD Workbench')).toBeTruthy()
  expect(await screen.findByRole('heading', { name: 'Emisor → canal → receptor' })).toBeTruthy()
  expect((screen.getByLabelText('Medio físico') as HTMLSelectElement).value).toBe('fiber')
  expect(screen.getByRole('button', { name: /Diseñar/ }).getAttribute('aria-current')).toBe('page')
  expect(screen.queryByRole('heading', { name: 'Fibra telecom' })).toBeNull()

  await waitFor(() => {
    const urls = api.fetchMock.mock.calls.map(([input]) => String(input))
    expect(urls.filter((url) => url === '/api/scenarios/inspect')).toHaveLength(1)
    expect(urls).not.toContain('/api/scenarios/validate')
    expect(urls.some((url) => url.startsWith('/api/characterize/'))).toBe(false)
    expect(urls).not.toContain('/api/dynamics/preview')
  })
})

test('selects fiber, edits distance, executes an immutable snapshot and detects a dirty draft', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)

  const distance = (await screen.findAllByLabelText(/Distancia/)).find((element) => (element as HTMLInputElement).type === 'number') as HTMLInputElement
  fireEvent.change(distance, { target: { value: '40' } })

  expect(await screen.findByText(/digest-40/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Ejecutar experimento' }))

  expect(await screen.findByText('CLAVE ESTIMADA')).toBeTruthy()
  expect(screen.getAllByText(/digest-40/).length).toBeGreaterThan(0)
  expect(screen.queryByText('SEGURO')).toBeNull()
  expect(screen.queryByText('secure')).toBeNull()
  expect(useDesignerStore.getState().runs.at(-1)?.digest).toBe('digest-40')
  expect(useDesignerStore.getState().runs.at(-1)?.scenario.channel.distance_km).toBe(40)

  fireEvent.change(screen.getByLabelText('Nombre del experimento'), { target: { value: 'Fibra renombrada' } })
  expect(screen.getAllByText('Cambios sin guardar').length).toBeGreaterThan(0)
  expect(screen.queryAllByText('Cambios sin ejecutar')).toHaveLength(0)

  fireEvent.change(distance, { target: { value: '45' } })
  expect(await screen.findByText('Cambios sin ejecutar')).toBeTruthy()
  expect(await screen.findByText(/digest-45/)).toBeTruthy()
  expect(useDesignerStore.getState().runs.at(-1)?.digest).toBe('digest-40')
})

test('sticky execute action reaches the execution controller', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)
  fireEvent.click((await screen.findAllByRole('button', { name: 'Ejecutar' })).at(-1) as HTMLButtonElement)

  expect(await screen.findByText('CLAVE ESTIMADA')).toBeTruthy()
  expect(useDesignerStore.getState().runs).toHaveLength(1)
})

test('loads a prepared experiment immediately without discarding completed runs', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)

  fireEvent.click(await screen.findByRole('button', { name: 'Ejecutar experimento' }))
  expect(await screen.findByText('CLAVE ESTIMADA')).toBeTruthy()
  expect(useDesignerStore.getState().runs).toHaveLength(1)

  const underwater = screen.getByRole('button', { name: /Submarino/ })
  fireEvent.click(underwater)

  await waitFor(() => expect(useDesignerStore.getState().activeMediumId).toBe('underwater'))
  expect(useDesignerStore.getState().scenario.channel.kind).toBe('underwater')
  await waitFor(() => expect(underwater.getAttribute('aria-pressed')).toBe('true'))
  expect(useDesignerStore.getState().runs).toHaveLength(1)
  expect(screen.queryByText(/Cambiar a Submarino/)).toBeNull()
})

test('keeps channel controls contextual and exposes full event retention next to execution', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)

  fireEvent.change(await screen.findByLabelText('Medio físico'), { target: { value: 'underwater' } })

  expect(await screen.findByLabelText('Turbidez / extinción del agua')).toBeTruthy()
  expect(screen.getByLabelText('Dispersión del agua')).toBeTruthy()
  expect(screen.queryByLabelText('Atenuación de la fibra')).toBeNull()

  const fullLog = screen.getByRole('checkbox', { name: /Conservar todos los eventos/ })
  fireEvent.click(fullLog)
  expect(useDesignerStore.getState().scenario.store_full_event_log).toBe(true)
  expect(screen.queryByLabelText('Tamaño de la muestra de eventos')).toBeNull()
})

test('asks before replacing an edited draft when changing medium', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)

  const distance = (await screen.findAllByLabelText(/Distancia/)).find((element) => (element as HTMLInputElement).type === 'number') as HTMLInputElement
  fireEvent.change(distance, { target: { value: '41' } })
  fireEvent.click(screen.getByRole('button', { name: /Submarino/ }))

  expect(await screen.findByRole('dialog', { name: 'Confirmar cambio de medio' })).toBeTruthy()
  expect(screen.getByText(/Se conservarán los resultados y curvas/)).toBeTruthy()
  expect(screen.getByText(/Se perderán los cambios de campos/)).toBeTruthy()
  expect(useDesignerStore.getState().activeMediumId).toBe('fiber')

  fireEvent.click(screen.getByRole('button', { name: 'Cambiar y descartar borrador' }))
  await waitFor(() => expect(useDesignerStore.getState().activeMediumId).toBe('underwater'))
  expect(useDesignerStore.getState().hasUnsavedChanges).toBe(true)

  fireEvent.click(screen.getByRole('button', { name: 'Satélite' }))
  expect(await screen.findByRole('dialog', { name: 'Confirmar cambio de medio' })).toBeTruthy()
  expect(useDesignerStore.getState().activeMediumId).toBe('underwater')
})

test('keeps the last inspection visible while a changed scenario is being revalidated', async () => {
  const api = mockPanelFetch()
  let inspectionCalls = 0
  let resolveInspection: ((response: Response) => void) | undefined
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input) !== '/api/scenarios/inspect') return api.fetchMock(input, init)
    inspectionCalls += 1
    const scenario = requestScenario(init)
    if (inspectionCalls === 1) return jsonResponse(inspectionResponse(scenario))
    return new Promise<Response>((resolve) => {
      resolveInspection = resolve
    })
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)

  const initialDigest = digestFor(useDesignerStore.getState().scenario)
  expect(await screen.findByText(`snapshot ${initialDigest}`)).toBeTruthy()
  const distance = (await screen.findAllByLabelText(/Distancia/)).find((element) => (element as HTMLInputElement).type === 'number') as HTMLInputElement
  fireEvent.change(distance, { target: { value: '40' } })
  await waitFor(() => expect(inspectionCalls).toBe(2))

  expect(screen.getByText(`snapshot ${initialDigest}`)).toBeTruthy()
  expect(screen.queryByText('snapshot pendiente')).toBeNull()

  resolveInspection?.(jsonResponse(inspectionResponse(useDesignerStore.getState().scenario)))
  expect(await screen.findByText('snapshot digest-40')).toBeTruthy()
})

test('opens advanced options in a stable overlay instead of expanding the page', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)
  render(<App />)

  const advancedChannel = (await screen.findAllByRole('button', { name: /Más ajustes de canal/ }))
    .find((button) => button.getAttribute('aria-haspopup') === 'dialog')
  fireEvent.click(advancedChannel as HTMLButtonElement)

  expect(await screen.findByRole('dialog', { name: 'Ajustes avanzados de Canal' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Cerrar Ajustes avanzados de Canal' }))
  expect(screen.queryByRole('dialog', { name: 'Ajustes avanzados de Canal' })).toBeNull()
})

test('reports library loading failures instead of pretending the library is empty', async () => {
  const api = mockPanelFetch()
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).startsWith('/api/experiments?')) {
      return { ok: false, status: 503, json: async () => ({ message: 'Servicio de experimentos no disponible' }) } as Response
    }
    return api.fetchMock(input, init)
  })
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)

  fireEvent.click(await screen.findByRole('button', { name: /Experimentos/ }))

  expect(await screen.findByText('Servicio de experimentos no disponible')).toBeTruthy()
  expect(screen.queryByText('No hay experimentos que coincidan')).toBeNull()
})

test('creates and exports a curve from an explicit base', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)
  const createObjectURL = vi.fn(() => 'blob:qkd-test')
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

  render(<App />)

  fireEvent.click(await screen.findByRole('button', { name: /Curvas/ }))
  expect(await screen.findByRole('heading', { name: 'Análisis y curvas' })).toBeTruthy()
  expect((screen.getByLabelText('Escenario base') as HTMLSelectElement).value).toBe('draft')
  expect((screen.getByLabelText('Receta guiada') as HTMLSelectElement).value).toBe('skr-distance')

  await waitFor(() => expect((screen.getByRole('button', { name: /Generar curva/ }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: /Generar curva/ }))

  expect(await screen.findByRole('heading', { name: 'Resumen descriptivo' })).toBeTruthy()
  expect(useDesignerStore.getState().curves.at(-1)?.baseDigest).toBe('draft')
  const csv = screen.getByRole('button', { name: 'CSV' })
  expect((csv as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(csv)
  expect(createObjectURL).toHaveBeenCalledTimes(1)
})

test('opens a guided curve with the completed run explicitly selected as its base', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)

  fireEvent.click(await screen.findByRole('button', { name: 'Ejecutar experimento' }))
  expect(await screen.findByText('CLAVE ESTIMADA')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /Tasa de clave estimada frente a distancia/ }))

  expect(await screen.findByRole('heading', { name: 'Análisis y curvas' })).toBeTruthy()
  expect((screen.getByLabelText(/Escenario base/) as HTMLSelectElement).value).toBe('run:run-test')
  expect(screen.getByText(/Este run es el punto de partida/)).toBeTruthy()
  expect(screen.getByText(/una curva necesita calcular nuevos puntos/i)).toBeTruthy()
})

test('saves, rejects an invalid import and opens the saved experiment from the library', async () => {
  const api = mockPanelFetch()
  vi.stubGlobal('fetch', api.fetchMock)

  render(<App />)

  const name = await screen.findByLabelText('Nombre del experimento')
  fireEvent.change(name, { target: { value: 'Experimento trazable' } })
  fireEvent.click(screen.getAllByRole('button', { name: 'Guardar' }).at(-1) as HTMLButtonElement)
  expect(await screen.findByText(/Experimento guardado como/)).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: /Experimentos/ }))
  expect(await screen.findByRole('heading', { name: 'Biblioteca de experimentos' })).toBeTruthy()
  expect(await screen.findByRole('heading', { name: 'Experimento trazable' })).toBeTruthy()

  const invalidFile = new File(['{"scenario":'], 'incompleto.qkd.json', { type: 'application/json' })
  Object.defineProperty(invalidFile, 'text', { value: async () => '{"scenario":' })
  fireEvent.change(screen.getByLabelText('Importar experimento'), { target: { files: [invalidFile] } })
  expect(await screen.findByText(/JSON inválido/)).toBeTruthy()
  expect(screen.getByText(/Elige un archivo JSON completo exportado/)).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: 'Abrir' }))
  await waitFor(() => expect((screen.getByLabelText('Nombre del experimento') as HTMLInputElement).value).toBe('Experimento trazable'))
  expect(useDesignerStore.getState().sourceExperimentId).toBe('exp-1')
})

function mockPanelFetch() {
  const saved: Experiment[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url === '/api/health') return jsonResponse({ status: 'ok', service: 'qiskit-qkd-panel' })
    if (url === '/api/catalog') return jsonResponse(catalogResponse())
    if (url === '/api/scenarios/inspect') {
      const scenario = requestScenario(init)
      return jsonResponse(inspectionResponse(scenario))
    }
    if (url === '/api/runs/estimate') return jsonResponse(costEstimate(1))
    if (url === '/api/runs' && method === 'POST') {
      const scenario = requestScenario(init)
      return jsonResponse({ job_id: 'run-test', status: 'queued', digest: digestFor(scenario), cost_estimate: costEstimate(1) })
    }
    if (url === '/api/runs/run-test') {
      return jsonResponse({
        job_id: 'run-test',
        status: 'done',
        progress: { done: 1, total: 1 },
        elapsed_s: 0.2,
        result_summary: resultSummary(),
      })
    }
    if (url === '/api/runs/run-test/result') return jsonResponse({ provenance: { backend: 'statevector' } })
    if (url === '/api/sweeps/estimate') return jsonResponse(sweepCostEstimate(25))
    if (url === '/api/sweeps' && method === 'POST') return jsonResponse({ job_id: 'sweep-test', status: 'queued', cost_estimate: sweepCostEstimate(25) })
    if (url === '/api/sweeps/sweep-test') {
      return jsonResponse({
        job_id: 'sweep-test',
        status: 'done',
        progress: { done: 25, total: 25 },
        elapsed_s: 0.4,
      })
    }
    if (url === '/api/sweeps/sweep-test/result') {
      return jsonResponse({
          rows: [
            { 'channel.distance_km': 0, secret_key_rate_bps: 1200, seed: 7 },
            { 'channel.distance_km': 120, secret_key_rate_bps: 15, seed: 31 },
          ],
          summary: [
            { 'channel.distance_km': 0, secret_key_rate_bps_mean: 1200, secret_key_rate_bps_p05: 1200, secret_key_rate_bps_p95: 1200 },
            { 'channel.distance_km': 120, secret_key_rate_bps_mean: 15, secret_key_rate_bps_p05: 15, secret_key_rate_bps_p95: 15 },
          ],
      })
    }
    if (url === '/api/experiments' && method === 'POST') {
      const body = parseBody(init)
      const scenario = body.scenario as ScenarioPayload
      const now = '2026-08-09T12:00:00Z'
      const experiment: Experiment = {
        id: 'exp-1',
        origin: 'user',
        name: String(body.name),
        schema_version: Number(body.schema_version ?? 2),
        digest: digestFor(scenario),
        scenario: structuredClone(scenario),
        tags: body.tags as string[],
        created_at: now,
        updated_at: now,
        last_result: (body.last_result ?? null) as JsonObject | null,
        curve_recipes: body.curve_recipes as JsonObject[],
        runs: body.runs as JsonObject[],
        curves: body.curves as JsonObject[],
        provenance: body.provenance as JsonObject,
      }
      saved.splice(0, saved.length, experiment)
      return jsonResponse({ experiment })
    }
    if (url.startsWith('/api/experiments?')) return jsonResponse({ experiments: saved, pagination: { offset: 0, limit: 50, total: saved.length, has_more: false } })
    if (url === '/api/presets') return jsonResponse({ presets: [] })
    throw new Error(`Unexpected ${method} URL: ${url}`)
  })
  return { fetchMock, saved }
}

function catalogResponse() {
  return {
    sections: [
      {
        key: 'channel',
        label_es: 'Canal',
        fields: [
          field('channel.kind', 'Familia de canal', 'select', 'fiber', null, { options: ['ideal', 'fiber', 'underwater'] }),
          field('channel.distance_km', 'Distancia', 'number', 25, 'km', { min: 0, max: 120 }),
          field('channel.attenuation_db_km', 'Atenuación', 'number', 0.2, 'dB/km', { min: 0, max: 10 }),
          field('channel.underwater_extinction_m_inv', 'Extinción submarina', 'number', 0.05, 'm⁻¹', { min: 0, max: 1 }),
          field('channel.underwater_scattering_broadening_ns_per_m', 'Scattering submarino', 'number', 0.008, 'ns/m', { min: 0, max: 1 }),
        ],
      },
    ],
    metrics: [
      { key: 'secret_key_rate_bps', label_es: 'Tasa de clave estimada', unit: 'bit/s' },
      { key: 'qber', label_es: 'QBER observado', unit: null },
    ],
    capabilities: {
      parameters: {
        'channel.distance_km': { effect_status: 'active', effect_reason: 'Modifica la pérdida de propagación.' },
      },
      metrics: {},
    },
  }
}

function field(
  key: string,
  label_es: string,
  type: string,
  defaultValue: unknown,
  unit: string | null = null,
  extra: JsonObject = {},
) {
  return { key, label_es, type, unit, default: defaultValue, sweepable: true, ...extra }
}

function inspectionResponse(scenario: ScenarioPayload) {
  const digest = digestFor(scenario)
  return {
    valid: true,
    digest,
    effective_digest: digest,
    scenario: structuredClone(scenario),
    effective_scenario: structuredClone(scenario),
    resolution_time_s: 0,
    warnings: [],
    characterizations: {
      source: { emitted_state: 'weak_coherent' },
      channel: { loss_db: Number(scenario.channel.distance_km) * 0.2, transmittance: 0.48 },
      detector: { p_dark_per_gate: 0.000001 },
      timing: { resolution_time_s: 0 },
    },
    cost_estimate: costEstimate(1),
  }
}

function resultSummary(): JsonObject {
  return {
    assessment: {
      data_status: 'available',
      key_status: 'estimated_key_available',
      qber_defined: true,
      qber_value: 0.02,
      rate_estimate_bps: 800,
      rate_estimate_status: 'available',
      reasons: ['La muestra contiene bits cribados observables.'],
      sample_size: 400,
      security_scope: 'pedagogical_asymptotic_diagnostic',
    },
    metrics: { abort: false, detected: 600, errors: 8, gain: 0.6, qber: 0.02, secure: true, sifted: 400 },
  }
}

function costEstimate(evaluations: number): CostEstimate {
  return {
    estimate_kind: 'upper_bound',
    evaluations,
    pulses_per_evaluation: 1024,
    total_pulse_events: 1024 * evaluations,
    estimated_max_circuits: 1024 * evaluations,
    shots_per_circuit: 1,
    estimated_max_shots: 1024 * evaluations,
    estimated_stored_events: 0,
    backend: 'statevector',
    full_event_log: false,
    warnings: [],
  }
}

function sweepCostEstimate(evaluations: number): SweepCostEstimate {
  return {
    ...costEstimate(evaluations),
    estimated_payload_bytes: 4_096,
    estimated_artifact_bytes: 4_096,
    estimated_total_bytes: 8_192,
  }
}

function requestScenario(init?: RequestInit): ScenarioPayload {
  return parseBody(init).scenario as ScenarioPayload
}

function parseBody(init?: RequestInit): JsonObject {
  return JSON.parse(String(init?.body ?? '{}')) as JsonObject
}

function digestFor(scenario: ScenarioPayload): string {
  return `digest-${Number(scenario.channel.distance_km)}`
}

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}
