import { defineConfig, devices } from '@playwright/test'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const configDirectory = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(configDirectory, '..', '..')
const configuredPort = Number.parseInt(process.env.QKD_E2E_PORT ?? '18180', 10)
if (!Number.isInteger(configuredPort) || configuredPort < 1 || configuredPort > 65_535) {
  throw new Error(`QKD_E2E_PORT must be an integer between 1 and 65535; received ${process.env.QKD_E2E_PORT ?? '18180'}`)
}

const runToken = process.env.QKD_E2E_RUN_TOKEN ?? `${process.pid}-${Date.now()}`
if (runToken.length > 64 || !/^[A-Za-z0-9_-]+$/.test(runToken)) {
  throw new Error('QKD_E2E_RUN_TOKEN must be 1-64 letters, numbers, underscores, or hyphens')
}
process.env.QKD_E2E_RUN_TOKEN = runToken
const localPython = process.platform === 'win32'
  ? path.join(repositoryRoot, '.venv', 'Scripts', 'python.exe')
  : path.join(repositoryRoot, '.venv', 'bin', 'python')
const python = process.env.QKD_E2E_PYTHON ?? (fs.existsSync(localPython) ? localPython : 'python')
const serverScript = path.join(repositoryRoot, 'scripts', 'run_e2e_panel.py')
const outputDir = process.env.QKD_E2E_OUTPUT_DIR ?? path.join(os.tmpdir(), 'qkd-panel-playwright')

export default defineConfig({
  testDir: path.join(configDirectory, 'e2e'),
  outputDir,
  globalTeardown: path.join(configDirectory, 'e2e', 'global-teardown.ts'),
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  timeout: 90_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: `http://127.0.0.1:${configuredPort}`,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `"${python}" "${serverScript}" --serve --port ${configuredPort}`,
    cwd: repositoryRoot,
    env: {
      ...process.env,
      QKD_E2E_PORT: String(configuredPort),
      QKD_E2E_RUN_TOKEN: runToken,
    },
    url: `http://127.0.0.1:${configuredPort}/api/health`,
    timeout: 120_000,
    reuseExistingServer: false,
  },
})
