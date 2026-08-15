import { expect, test, type Page } from '@playwright/test'

const fiberButton = (page: Page) => page.getByRole('button', { name: /^Fibra\b/i })

async function openFresh(page: Page): Promise<void> {
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await expect(page.getByText('QKD Workbench')).toBeVisible()
}

async function runWithOptionalCostConfirmation(page: Page): Promise<void> {
  const runButton = page.getByRole('button', { name: 'Ejecutar experimento', exact: true })
  await expect(runButton).toBeEnabled()
  await runButton.click()
  const confirmation = page.getByRole('button', { name: 'Ejecutar con esta cota', exact: true })
  try {
    await confirmation.waitFor({ state: 'visible', timeout: 1_000 })
    await confirmation.click()
  } catch {
    // Most small E2E scenarios do not need the high-cost confirmation dialog.
  }
}

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

async function assertNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)
  expect(overflow, 'the rendered document must not overflow horizontally').toBeTruthy()
}

test.describe('QKD panel user journeys', () => {
  test('configures fibre, runs, persists, reloads, and recovers the result from the library', async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page)
    await openFresh(page)
    await expect(page.getByRole('navigation', { name: 'Vistas principales' })).toBeVisible()

    // The prepared-medium picker is an observable user boundary; clicking the
    // fibre preset replaces the draft with the canonical fibre scenario.
    await expect(fiberButton(page)).toBeVisible()
    await fiberButton(page).click()
    await expect(page.getByRole('button', { name: 'Cambiar medio', exact: true })).toBeVisible()

    const distance = page.getByLabel('Distancia del enlace', { exact: true })
    await expect(distance).toBeVisible()
    await distance.fill('42')
    await expect(distance).toHaveValue('42')
    await expect(page.getByText('Configuración válida', { exact: true })).toBeVisible()

    const pulses = page.locator('input[aria-label*="pulsos"]')
    await pulses.fill('32')
    await expect(page.getByText('Configuración válida', { exact: true })).toBeVisible()

    await runWithOptionalCostConfirmation(page)
    // A tiny 32-pulse job can finish between two browser paints; the persisted
    // result heading and metric are the stable observable completion boundary.
    await expect(page.getByRole('heading', { name: 'Ejecución principal', exact: true })).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('#execution-panel article').filter({ hasText: /^Detecciones/ }).first()).toBeVisible()
    await assertNoHorizontalOverflow(page)

    const experimentName = 'E2E Fibra Persistente'
    await page.getByLabel('Nombre del experimento', { exact: true }).fill(experimentName)
    await page.getByRole('button', { name: 'Guardar', exact: true }).first().click()
    await expect(page.getByText(/Experimento guardado como/)).toBeVisible()

    await page.reload()
    await expect(page.getByLabel('Nombre del experimento', { exact: true })).toHaveValue(experimentName)
    await page.getByRole('button', { name: /^Experimentos\b/ }).click()
    await expect(page.getByRole('heading', { name: 'Biblioteca de experimentos', exact: true })).toBeVisible()
    const savedRow = page.getByRole('article').filter({ hasText: experimentName })
    await expect(savedRow).toBeVisible()
    await savedRow.getByRole('button', { name: 'Abrir', exact: true }).click()
    await expect(page.getByLabel('Nombre del experimento', { exact: true })).toHaveValue(experimentName)
    await expect(page.locator('#execution-panel article').filter({ hasText: /^Detecciones/ }).first()).toBeVisible()
    await assertNoHorizontalOverflow(page)
    expect(consoleErrors, 'the happy-path interaction must not emit browser errors').toEqual([])
  })

  test('renders an accessible, non-overflowing mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await openFresh(page)
    await expect(page.getByRole('main')).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Vistas principales' })).toBeVisible()
    await expect(fiberButton(page)).toBeVisible()
    await fiberButton(page).click()
    await expect(page.getByRole('button', { name: 'Cambiar medio', exact: true })).toBeVisible()
    await assertNoHorizontalOverflow(page)
    await page.keyboard.press('Tab')
    await expect(page.locator(':focus')).toBeVisible()
  })

  test('shows the offline boundary and prevents execution', async ({ page }) => {
    await page.route('**/api/health', (route) => route.abort('failed'))
    await page.route('**/api/catalog', (route) => route.abort('failed'))
    await page.route('**/api/scenarios/inspect', (route) => route.abort('failed'))
    await page.goto('/')
    await expect(page.getByText('API no disponible', { exact: true })).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('button', { name: 'Ejecutar experimento', exact: true })).toBeDisabled()
    await expect(page.getByText(/La API no está disponible/i)).toBeVisible()
  })

  test('surfaces an interrupted job at the network/state boundary', async ({ page }) => {
    const createdAt = new Date().toISOString()
    const estimate = {
      estimate_kind: 'upper_bound',
      evaluations: 1,
      pulses_per_evaluation: 16,
      total_pulse_events: 16,
      estimated_max_circuits: 1,
      shots_per_circuit: 16,
      estimated_max_shots: 16,
      estimated_stored_events: 16,
      backend: 'statevector',
      full_event_log: false,
      warnings: [],
    }
    await page.route('**/api/runs', async (route) => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: 'e2e-interrupted', status: 'queued', digest: 'e2e-digest', cost_estimate: estimate }),
      })
    })
    await page.route('**/api/runs/e2e-interrupted', async (route) => {
      if (route.request().method() !== 'GET') return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'e2e-interrupted',
          kind: 'run',
          status: 'interrupted',
          progress: { done: 16, total: 16 },
          elapsed_s: 0.1,
          timestamps: { created_at: createdAt, updated_at: createdAt },
          error: 'Job was interrupted by a service restart.',
          error_code: 'INTERRUPTED',
          issues: [],
        }),
      })
    })
    // Python API tests exercise real persistence/restart recovery.  This E2E
    // case deliberately mocks only the HTTP state boundary to keep the browser
    // test deterministic and avoid creating a second long-running worker.
    await openFresh(page)
    await page.locator('input[aria-label*="pulsos"]').fill('16')
    await expect(page.getByText('Configuración válida', { exact: true })).toBeVisible()
    await runWithOptionalCostConfirmation(page)
    await expect(page.getByRole('progressbar')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(/Interrumpido al reiniciar/)).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })
})
