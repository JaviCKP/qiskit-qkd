# QKD Medium-First Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a visual, medium-first QKD dashboard where the user chooses Ideal, Fiber, Vacuum, Air, Satellite, Underwater, or Custom; each non-custom medium shows realistic defaults and only relevant controls; curves and temporal dynamics are created through simple recipes while preserving full expert granularity.

**Architecture:** Keep the FastAPI scenario model and existing API endpoints. Move frontend domain decisions into focused TypeScript modules: medium definitions, field visibility, curve recipes, temporal patterns, and cockpit/gallery components. Integrate those modules into `PanelShell` while extracting large view components from `App.tsx` as the implementation touches them.

**Tech Stack:** React 18, TypeScript, Vite, TanStack Query, Zustand, Plotly, lucide-react, FastAPI, pytest, Vitest, ESLint.

---

## Current State And Constraints

- Worktree branch: `codex/qkd-dashboard-panel`.
- The branch already has two spec commits:
  - `46b79f2 spec medium-first dashboard redesign`
  - `febd87a refine dashboard spec with guided ideal workflows`
- There are pre-existing local modifications in:
  - `panel/api/app.py`
  - `panel/api/runtime.py`
  - `src/qiskit_qkd/backends/qiskit_sampler.py`
  - `tests/panel_api/test_phase2.py`
- Preserve those local changes. Do not stage them unless a task explicitly edits that same file.
- Do not use `git add .`. Stage exact files in every commit.
- Use `apply_patch` for manual file edits.

## File Structure

Create or modify these files:

- Create `panel/web/src/features/shared/scenarioPaths.ts`
  - Shared `readTarget`, `writeTarget`, `isRecord`, and clone helpers.
- Create `panel/web/src/features/shared/scenarioPaths.test.ts`
  - Unit coverage for nested scenario access and immutable writes.
- Create `panel/web/src/features/lab/mediums.ts`
  - Medium IDs, definitions, realistic scenario overrides, medium inference, and gallery metadata.
- Create `panel/web/src/features/lab/mediums.test.ts`
  - Unit coverage for medium list, defaults, and inference.
- Create `panel/web/src/features/designer/defaultScenario.ts`
  - Existing `defaultScenario` object moved out of the Zustand store so medium definitions can reuse it without import cycles.
- Modify `panel/web/src/features/designer/scenarioStore.ts`
  - Import `defaultScenario` from the new file.
- Create `panel/web/src/features/designer/fieldVisibility.ts`
  - Medium-specific filtering plus catalog `visible_when` support.
- Create `panel/web/src/features/designer/fieldVisibility.test.ts`
  - Unit coverage for Fiber, Ideal, Air/Satellite, Underwater, and Custom filtering.
- Create `panel/web/src/features/curves/recipes.ts`
  - Plain-language curve recipes and sweep-axis generation.
- Create `panel/web/src/features/curves/recipes.test.ts`
  - Unit coverage for generated axis payloads and readable descriptions.
- Create `panel/web/src/features/dynamics/temporalPatterns.ts`
  - Named temporal patterns mapped to existing dynamic schedule payloads.
- Create `panel/web/src/features/dynamics/temporalPatterns.test.ts`
  - Unit coverage for stable, degradation, recovery, drift, and burst patterns.
- Create `panel/web/src/features/lab/MediumGallery.tsx`
  - Visual medium cards and actions.
- Create `panel/web/src/features/lab/LinkCockpit.tsx`
  - Source -> Medium -> Detector -> Post-processing cockpit and live metric tiles.
- Create `panel/web/src/features/designer/FocusedInspector.tsx`
  - Filtered granular editor with search and expert toggle.
- Create `panel/web/src/features/curves/CurveRecipeBar.tsx`
  - Recipe-first curve controls with advanced axis expansion.
- Create `panel/web/src/features/dynamics/TemporalPatternBuilder.tsx`
  - Simple temporal pattern UI with generated schedule preview.
- Modify `panel/web/src/features/designer/scenarioStore.ts`
  - Add active medium state and metadata-aware scenario loading.
- Modify `panel/web/src/App.tsx`
  - Replace first screen with `Laboratorio`, wire gallery, cockpit, inspector, curve recipes, and temporal patterns.
- Modify `panel/web/src/App.test.tsx`
  - Update smoke test to prove the medium-first first screen and filtered controls.
- Modify `panel/web/src/index.css`
  - Add polished scientific dashboard base styles only if Tailwind classes are insufficient.
- Modify `panel/api/runtime.py`
  - Ensure `/api/presets` includes an Ideal preset and realistic medium presets. Preserve existing uncommitted real-preset work.
- Modify `tests/panel_api/test_phase2.py`
  - Update preset count/name tests only after backend preset behavior is finalized.

---

### Task 1: Shared Scenario Path Utilities

**Files:**
- Create: `panel/web/src/features/shared/scenarioPaths.ts`
- Create: `panel/web/src/features/shared/scenarioPaths.test.ts`

- [ ] **Step 1: Write the failing test**

Create `panel/web/src/features/shared/scenarioPaths.test.ts`:

```ts
import { expect, test } from 'vitest'

import { cloneJson, isRecord, readTarget, writeTarget } from './scenarioPaths'

test('reads root and nested scenario targets', () => {
  const scenario = {
    pulses: 1024,
    channel: { kind: 'fiber', distance_km: 25 },
  }

  expect(readTarget(scenario, 'scenario.pulses')).toBe(1024)
  expect(readTarget(scenario, 'channel.kind')).toBe('fiber')
  expect(readTarget(scenario, 'channel.distance_km')).toBe(25)
  expect(readTarget(scenario, 'channel.missing')).toBeUndefined()
})

test('writes targets immutably', () => {
  const scenario = {
    pulses: 1024,
    channel: { kind: 'fiber', distance_km: 25 },
  }

  const next = writeTarget(scenario, 'channel.distance_km', 80)

  expect(next).toEqual({
    pulses: 1024,
    channel: { kind: 'fiber', distance_km: 80 },
  })
  expect(scenario.channel.distance_km).toBe(25)
})

test('supports scenario-prefixed root writes', () => {
  const next = writeTarget({ pulses: 1024 }, 'scenario.pulses', 4096)

  expect(next).toEqual({ pulses: 4096 })
})

test('recognizes records and clones JSON-safe values', () => {
  const original = { channel: { kind: 'ideal' }, rows: [1, 2] }
  const cloned = cloneJson(original)

  expect(isRecord(original)).toBe(true)
  expect(isRecord([1, 2])).toBe(false)
  expect(cloned).toEqual(original)
  expect(cloned).not.toBe(original)
  expect(cloned.channel).not.toBe(original.channel)
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/shared/scenarioPaths.test.ts
```

Expected: FAIL because `src/features/shared/scenarioPaths.ts` does not exist.

- [ ] **Step 3: Implement the utility module**

Create `panel/web/src/features/shared/scenarioPaths.ts`:

```ts
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function readTarget(
  scenario: Record<string, unknown>,
  target: string,
): unknown {
  const [section, field] = target.split('.')
  if (!section || !field) {
    return undefined
  }
  if (section === 'scenario') {
    return scenario[field]
  }
  const sectionValue = scenario[section]
  if (!isRecord(sectionValue)) {
    return undefined
  }
  return sectionValue[field]
}

export function writeTarget(
  scenario: Record<string, unknown>,
  target: string,
  value: unknown,
): Record<string, unknown> {
  const [section, field] = target.split('.')
  if (!section || !field) {
    return scenario
  }
  if (section === 'scenario') {
    return { ...scenario, [field]: value }
  }
  const sectionValue = scenario[section]
  if (!isRecord(sectionValue)) {
    return scenario
  }
  return {
    ...scenario,
    [section]: {
      ...sectionValue,
      [field]: value,
    },
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/shared/scenarioPaths.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add panel/web/src/features/shared/scenarioPaths.ts panel/web/src/features/shared/scenarioPaths.test.ts
git commit -m "add shared scenario path utilities"
```

---

### Task 2: Medium Definitions And Realistic Defaults

**Files:**
- Create: `panel/web/src/features/lab/mediums.ts`
- Create: `panel/web/src/features/lab/mediums.test.ts`
- Create: `panel/web/src/features/designer/defaultScenario.ts`
- Modify: `panel/web/src/features/designer/scenarioStore.ts`

- [ ] **Step 1: Write the failing test**

Create `panel/web/src/features/lab/mediums.test.ts`:

```ts
import { expect, test } from 'vitest'

import {
  inferMediumFromScenario,
  mediumDefinitions,
  mediumOptions,
  scenarioForMedium,
} from './mediums'

test('exposes all approved medium choices in display order', () => {
  expect(mediumOptions.map((medium) => medium.id)).toEqual([
    'ideal',
    'fiber',
    'vacuum',
    'air',
    'satellite',
    'underwater',
    'custom',
  ])
})

test('builds realistic medium scenarios without sharing object references', () => {
  const fiber = scenarioForMedium('fiber')
  const secondFiber = scenarioForMedium('fiber')

  expect(fiber.channel).toMatchObject({
    kind: 'fiber',
    distance_km: 100,
    attenuation_db_km: 0.2,
    wavelength_nm: 1550,
  })
  expect(fiber.detector).toMatchObject({
    kind: 'threshold',
    efficiency: 0.85,
    dark_count_rate_hz: 10,
  })
  expect(fiber.source).toMatchObject({ kind: 'decoy_weak_coherent' })
  expect(fiber.metadata).toMatchObject({ mediumId: 'fiber' })
  expect(secondFiber).not.toBe(fiber)
  expect(secondFiber.channel).not.toBe(fiber.channel)
})

test('keeps ideal channel clean and quick', () => {
  const ideal = scenarioForMedium('ideal')

  expect(ideal.channel).toMatchObject({
    kind: 'ideal',
    distance_km: 0,
    attenuation_db_km: 0,
    background_count_rate_hz: 0,
  })
  expect(ideal.pulses).toBe(1024)
  expect(ideal.metadata).toMatchObject({ mediumId: 'ideal' })
})

test('infers medium from metadata before channel kind', () => {
  expect(
    inferMediumFromScenario({
      metadata: { mediumId: 'satellite' },
      channel: { kind: 'free_space' },
    }),
  ).toBe('satellite')
})

test('infers medium from channel kind when metadata is absent', () => {
  expect(inferMediumFromScenario({ channel: { kind: 'ideal' } })).toBe('ideal')
  expect(inferMediumFromScenario({ channel: { kind: 'fiber' } })).toBe('fiber')
  expect(inferMediumFromScenario({ channel: { kind: 'underwater' } })).toBe('underwater')
  expect(inferMediumFromScenario({ channel: { kind: 'free_space' } })).toBe('air')
  expect(inferMediumFromScenario({ channel: { kind: 'space' } })).toBe('vacuum')
})

test('medium definitions include card copy and default curve recipes', () => {
  for (const medium of mediumOptions) {
    expect(mediumDefinitions[medium.id].label).toBeTruthy()
    expect(mediumDefinitions[medium.id].summary).toBeTruthy()
    expect(mediumDefinitions[medium.id].defaultCurveRecipeId).toBeTruthy()
  }
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/lab/mediums.test.ts
```

Expected: FAIL because `src/features/lab/mediums.ts` does not exist.

- [ ] **Step 3: Move the default scenario object**

Create `panel/web/src/features/designer/defaultScenario.ts` by moving the existing exported `defaultScenario` object from `panel/web/src/features/designer/scenarioStore.ts` into this file. Keep the object content byte-for-byte the same. The new file starts with:

```ts
import type { ScenarioPayload } from '@/api/client'

export const defaultScenario: ScenarioPayload = {
```

The closing `}` of the existing object stays the closing `}` in the new file.

Then update the top of `panel/web/src/features/designer/scenarioStore.ts`:

```ts
import { create } from 'zustand'

import type { ScenarioPayload } from '@/api/client'
import { defaultScenario } from './defaultScenario'
```

After this step, `scenarioStore.ts` still exports `useDesignerStore`, and code that imports `defaultScenario` from `scenarioStore.ts` will be updated in the next step.

- [ ] **Step 4: Implement the medium module**

Create `panel/web/src/features/lab/mediums.ts`:

```ts
import type { ScenarioPayload } from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'
import { cloneJson, isRecord, readTarget } from '@/features/shared/scenarioPaths'

export type MediumId =
  | 'ideal'
  | 'fiber'
  | 'vacuum'
  | 'air'
  | 'satellite'
  | 'underwater'
  | 'custom'

export type MediumDefinition = {
  id: MediumId
  label: string
  shortLabel: string
  summary: string
  channelKinds: string[]
  icon: 'sparkles' | 'cable' | 'orbit' | 'cloud' | 'satellite' | 'waves' | 'sliders'
  accentClass: string
  expectedRange: string
  detectorLabel: string
  realismLabel: string
  defaultCurveRecipeId: string
  scenario: ScenarioPayload
}

const idealScenario = mergeScenario({
  pulses: 1024,
  clock_rate_hz: 1_000_000,
  seed: 1,
  source: {
    kind: 'ideal_single_photon',
    emission_probability: 1,
    mean_photon_number: null,
    preparation_error_probability: 0,
  },
  channel: {
    kind: 'ideal',
    distance_km: 0,
    attenuation_db_km: 0,
    fixed_loss_db: 0,
    background_count_rate_hz: 0,
    depolarizing_probability: 0,
    phase_damping_probability: 0,
  },
  detector: {
    kind: 'ideal',
    efficiency: 1,
    dark_count_rate_hz: 0,
    gate_width_s: 1e-9,
    readout_error_probability: 0,
  },
  timing: { jitter_std_s: 0, clock_offset_s: 0, clock_drift_ppm: 0 },
  metadata: { mediumId: 'ideal', presetName: 'Canal ideal' },
})

const fiberScenario = mergeScenario({
  pulses: 10000,
  clock_rate_hz: 1_000_000_000,
  seed: 10,
  source: {
    kind: 'decoy_weak_coherent',
    preparation_error_probability: 0.001,
    decoy_intensities: [
      { name: 'signal', mean_photon_number: 0.6, selection_probability: 0.5 },
      { name: 'decoy', mean_photon_number: 0.2, selection_probability: 0.25 },
      { name: 'vacuum', mean_photon_number: 0, selection_probability: 0.25 },
    ],
  },
  channel: {
    kind: 'fiber',
    distance_km: 100,
    attenuation_db_km: 0.2,
    wavelength_nm: 1550,
    chromatic_dispersion_ps_nm_km: 17,
    pmd_coefficient_ps_sqrt_km: 0.1,
    source_spectral_width_nm: 0.01,
    polarization_dependent_loss_db: 0.1,
    classical_channel_power_mw: 0,
    raman_coefficient_hz_mw_km: 0,
    raman_filter_isolation_db: 0,
  },
  detector: {
    kind: 'threshold',
    efficiency: 0.85,
    dark_count_rate_hz: 10,
    gate_width_s: 1e-9,
    dead_time_s: 20e-9,
    afterpulse_probability: 0.001,
  },
  timing: { jitter_std_s: 50e-12 },
  metadata: { mediumId: 'fiber', presetName: 'Telecom fibra 100 km SNSPD' },
})

const vacuumScenario = mergeScenario({
  pulses: 10000,
  clock_rate_hz: 10_000_000,
  seed: 20,
  channel: {
    kind: 'space',
    distance_km: 1000,
    wavelength_nm: 1550,
    transmitter_aperture_m: 0.1,
    receiver_aperture_m: 0.5,
    beam_divergence_rad: 15e-6,
    background_count_rate_hz: 1,
  },
  detector: { kind: 'threshold', efficiency: 0.75, dark_count_rate_hz: 5 },
  metadata: { mediumId: 'vacuum', presetName: 'Vacio optico largo alcance' },
})

const airScenario = mergeScenario({
  pulses: 10000,
  clock_rate_hz: 10_000_000,
  seed: 30,
  channel: {
    kind: 'free_space',
    distance_km: 1.5,
    wavelength_nm: 850,
    atmospheric_extinction_db_km: 1,
    scintillation_sigma: 0.3,
    pointing_jitter_rad: 5e-6,
    background_count_rate_hz: 500,
    transmitter_aperture_m: 0.05,
    receiver_aperture_m: 0.15,
  },
  detector: {
    kind: 'threshold',
    efficiency: 0.5,
    dark_count_rate_hz: 50,
    gate_width_s: 1e-9,
    dead_time_s: 22e-9,
    afterpulse_probability: 0.005,
  },
  timing: { jitter_std_s: 350e-12 },
  metadata: { mediumId: 'air', presetName: 'Aire urbano 1.5 km SPAD' },
})

const satelliteScenario = mergeScenario({
  pulses: 10000,
  clock_rate_hz: 100_000_000,
  seed: 40,
  channel: {
    kind: 'free_space',
    distance_km: 500,
    wavelength_nm: 1550,
    atmospheric_extinction_db_km: 0.05,
    scintillation_sigma: 0.15,
    pointing_jitter_rad: 2e-6,
    background_count_rate_hz: 100,
    transmitter_aperture_m: 0.12,
    receiver_aperture_m: 0.8,
    beam_divergence_rad: 10e-6,
  },
  detector: { kind: 'threshold', efficiency: 0.75, dark_count_rate_hz: 20 },
  timing: { jitter_std_s: 100e-12 },
  metadata: { mediumId: 'satellite', presetName: 'Satelite LEO 500 km' },
})

const underwaterScenario = mergeScenario({
  pulses: 50000,
  clock_rate_hz: 1_000_000,
  seed: 50,
  source: { kind: 'weak_coherent', mean_photon_number: 0.5 },
  channel: {
    kind: 'underwater',
    distance_km: 0.03,
    wavelength_nm: 520,
    underwater_extinction_m_inv: 0.05,
    underwater_scattering_broadening_ns_per_m: 0.008,
    background_count_rate_hz: 200,
    transmitter_aperture_m: 0.03,
    receiver_aperture_m: 0.1,
  },
  detector: {
    kind: 'threshold',
    efficiency: 0.5,
    dark_count_rate_hz: 200,
    gate_width_s: 1e-9,
    dead_time_s: 50e-9,
    afterpulse_probability: 0.01,
  },
  metadata: { mediumId: 'underwater', presetName: 'Submarino 30 m agua clara' },
})

const customScenario = mergeScenario({
  metadata: { mediumId: 'custom', presetName: 'Custom' },
})

export const mediumDefinitions: Record<MediumId, MediumDefinition> = {
  ideal: {
    id: 'ideal',
    label: 'Canal ideal',
    shortLabel: 'Ideal',
    summary: 'Linea base pedagogica sin perdidas ni ruido de medio.',
    channelKinds: ['ideal'],
    icon: 'sparkles',
    accentClass: 'text-emerald-300 border-emerald-400/40 bg-emerald-400/10',
    expectedRange: '0 km efectivos',
    detectorLabel: 'Detector ideal',
    realismLabel: 'Baseline',
    defaultCurveRecipeId: 'ideal-baseline',
    scenario: idealScenario,
  },
  fiber: {
    id: 'fiber',
    label: 'Fibra telecom',
    shortLabel: 'Fibra',
    summary: 'SMF 1550 nm con SNSPD, dispersion, PMD y perdidas realistas.',
    channelKinds: ['fiber'],
    icon: 'cable',
    accentClass: 'text-cyan border-cyan/40 bg-cyan/10',
    expectedRange: '0-120 km',
    detectorLabel: 'SNSPD 85%',
    realismLabel: 'SMF-28',
    defaultCurveRecipeId: 'skr-distance',
    scenario: fiberScenario,
  },
  vacuum: {
    id: 'vacuum',
    label: 'Vacio',
    shortLabel: 'Vacio',
    summary: 'Enlace optico sin atmosfera con perdida geometrica.',
    channelKinds: ['space', 'deep_space', 'vacuum'],
    icon: 'orbit',
    accentClass: 'text-violet-300 border-violet-400/40 bg-violet-400/10',
    expectedRange: '10-1000 km',
    detectorLabel: 'SNSPD 75%',
    realismLabel: 'Libre de atmosfera',
    defaultCurveRecipeId: 'gain-pointing',
    scenario: vacuumScenario,
  },
  air: {
    id: 'air',
    label: 'Aire urbano',
    shortLabel: 'Aire',
    summary: 'Free-space terrestre con extincion, scintillation y jitter.',
    channelKinds: ['free_space', 'atmospheric'],
    icon: 'cloud',
    accentClass: 'text-sky-300 border-sky-400/40 bg-sky-400/10',
    expectedRange: '0.1-5 km',
    detectorLabel: 'Si-SPAD',
    realismLabel: 'Urbano',
    defaultCurveRecipeId: 'qber-atmosphere',
    scenario: airScenario,
  },
  satellite: {
    id: 'satellite',
    label: 'Satelite LEO',
    shortLabel: 'Satelite',
    summary: 'Enlace LEO con aperturas, pointing y atmosfera.',
    channelKinds: ['free_space', 'space'],
    icon: 'satellite',
    accentClass: 'text-amber-300 border-amber-400/40 bg-amber-400/10',
    expectedRange: '300-1200 km',
    detectorLabel: 'SNSPD 75%',
    realismLabel: 'LEO',
    defaultCurveRecipeId: 'gain-pointing',
    scenario: satelliteScenario,
  },
  underwater: {
    id: 'underwater',
    label: 'Submarino',
    shortLabel: 'Agua',
    summary: 'Canal azul-verde con extincion y scattering de agua clara.',
    channelKinds: ['underwater', 'water', 'marine'],
    icon: 'waves',
    accentClass: 'text-teal-300 border-teal-400/40 bg-teal-400/10',
    expectedRange: '1-50 m',
    detectorLabel: 'Si-SPAD',
    realismLabel: 'Jerlov I',
    defaultCurveRecipeId: 'gain-water-extinction',
    scenario: underwaterScenario,
  },
  custom: {
    id: 'custom',
    label: 'Custom experto',
    shortLabel: 'Custom',
    summary: 'Todos los parametros disponibles sin filtrado por medio.',
    channelKinds: ['ideal', 'fiber', 'space', 'free_space', 'underwater'],
    icon: 'sliders',
    accentClass: 'text-slate-200 border-slate-400/40 bg-white/5',
    expectedRange: 'Sin limite UI',
    detectorLabel: 'Editable',
    realismLabel: 'Experto',
    defaultCurveRecipeId: 'custom-axis',
    scenario: customScenario,
  },
}

export const mediumOptions = [
  mediumDefinitions.ideal,
  mediumDefinitions.fiber,
  mediumDefinitions.vacuum,
  mediumDefinitions.air,
  mediumDefinitions.satellite,
  mediumDefinitions.underwater,
  mediumDefinitions.custom,
]

export function scenarioForMedium(id: MediumId): ScenarioPayload {
  return cloneJson(mediumDefinitions[id].scenario)
}

export function inferMediumFromScenario(scenario: Record<string, unknown>): MediumId {
  const metadata = scenario.metadata
  const metadataMedium = isRecord(metadata) ? metadata.mediumId : undefined
  if (isMediumId(metadataMedium)) {
    return metadataMedium
  }
  const kind = String(readTarget(scenario, 'channel.kind') ?? 'ideal')
  if (kind === 'ideal') {
    return 'ideal'
  }
  if (kind === 'fiber') {
    return 'fiber'
  }
  if (kind === 'underwater' || kind === 'water' || kind === 'marine') {
    return 'underwater'
  }
  if (kind === 'space' || kind === 'deep_space' || kind === 'vacuum') {
    return 'vacuum'
  }
  if (kind === 'free_space' || kind === 'atmospheric' || kind === 'satellite') {
    return 'air'
  }
  return 'custom'
}

function isMediumId(value: unknown): value is MediumId {
  return typeof value === 'string' && value in mediumDefinitions
}

function mergeScenario(overrides: Record<string, unknown>): ScenarioPayload {
  return mergeRecords(defaultScenario, overrides) as ScenarioPayload
}

function mergeRecords(
  base: Record<string, unknown>,
  overrides: Record<string, unknown>,
): Record<string, unknown> {
  const next = cloneJson(base)
  for (const [key, value] of Object.entries(overrides)) {
    if (isRecord(value) && isRecord(next[key])) {
      next[key] = mergeRecords(next[key], value)
    } else {
      next[key] = cloneJson(value)
    }
  }
  return next
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/lab/mediums.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add panel/web/src/features/designer/defaultScenario.ts panel/web/src/features/designer/scenarioStore.ts panel/web/src/features/lab/mediums.ts panel/web/src/features/lab/mediums.test.ts
git commit -m "add medium definitions for dashboard"
```

---

### Task 3: Medium-Aware Field Visibility

**Files:**
- Create: `panel/web/src/features/designer/fieldVisibility.ts`
- Create: `panel/web/src/features/designer/fieldVisibility.test.ts`

- [ ] **Step 1: Write the failing test**

Create `panel/web/src/features/designer/fieldVisibility.test.ts`:

```ts
import { expect, test } from 'vitest'

import type { CatalogField } from '@/api/client'
import { visibleFieldsForMedium } from './fieldVisibility'

const fields = [
  field('channel.kind'),
  field('channel.distance_km'),
  field('channel.attenuation_db_km'),
  field('channel.chromatic_dispersion_ps_nm_km'),
  field('channel.pmd_coefficient_ps_sqrt_km'),
  field('channel.pointing_jitter_rad'),
  field('channel.scintillation_sigma'),
  field('channel.underwater_extinction_m_inv'),
  field('channel.underwater_scattering_broadening_ns_per_m'),
  field('detector.efficiency'),
  field('timing.jitter_std_s'),
  field('source.decoy_intensities', {
    visible_when: { target: 'source.kind', equals: 'decoy_weak_coherent' },
  }),
]

test('fiber shows fiber fields and hides air and underwater fields', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: { source: { kind: 'decoy_weak_coherent' } },
    expert: false,
    search: '',
  }).map((item) => item.key)

  expect(visible).toContain('channel.chromatic_dispersion_ps_nm_km')
  expect(visible).toContain('channel.pmd_coefficient_ps_sqrt_km')
  expect(visible).not.toContain('channel.pointing_jitter_rad')
  expect(visible).not.toContain('channel.underwater_extinction_m_inv')
})

test('ideal hides physical medium impairment fields', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'ideal',
    scenario: { source: { kind: 'ideal_single_photon' } },
    expert: false,
    search: '',
  }).map((item) => item.key)

  expect(visible).toContain('channel.kind')
  expect(visible).toContain('detector.efficiency')
  expect(visible).not.toContain('channel.attenuation_db_km')
  expect(visible).not.toContain('channel.pmd_coefficient_ps_sqrt_km')
  expect(visible).not.toContain('channel.scintillation_sigma')
  expect(visible).not.toContain('channel.underwater_extinction_m_inv')
})

test('custom and expert mode show all catalog-visible fields', () => {
  const custom = visibleFieldsForMedium({
    fields,
    mediumId: 'custom',
    scenario: { source: { kind: 'decoy_weak_coherent' } },
    expert: false,
    search: '',
  }).map((item) => item.key)
  const expert = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: { source: { kind: 'decoy_weak_coherent' } },
    expert: true,
    search: '',
  }).map((item) => item.key)

  expect(custom).toContain('channel.pointing_jitter_rad')
  expect(custom).toContain('channel.underwater_extinction_m_inv')
  expect(expert).toContain('channel.pointing_jitter_rad')
  expect(expert).toContain('channel.underwater_extinction_m_inv')
})

test('search can reveal hidden matching fields', () => {
  const visible = visibleFieldsForMedium({
    fields,
    mediumId: 'fiber',
    scenario: { source: { kind: 'ideal_single_photon' } },
    expert: false,
    search: 'pointing',
  }).map((item) => item.key)

  expect(visible).toEqual(['channel.pointing_jitter_rad'])
})

function field(key: string, overrides: Partial<CatalogField> = {}): CatalogField {
  return {
    key,
    label_es: key,
    type: 'number',
    unit: null,
    default: 0,
    sweepable: true,
    ...overrides,
  }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/designer/fieldVisibility.test.ts
```

Expected: FAIL because `fieldVisibility.ts` does not exist.

- [ ] **Step 3: Implement field visibility**

Create `panel/web/src/features/designer/fieldVisibility.ts`:

```ts
import type { CatalogField } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'
import { readTarget } from '@/features/shared/scenarioPaths'

type VisibleFieldsArgs = {
  fields: CatalogField[]
  mediumId: MediumId
  scenario: Record<string, unknown>
  expert: boolean
  search: string
}

const baseFields = new Set([
  'scenario.pulses',
  'scenario.clock_rate_hz',
  'scenario.seed',
  'scenario.event_sample_size',
  'protocol.name',
  'protocol.basis_choices',
  'source.kind',
  'source.emission_probability',
  'source.mean_photon_number',
  'source.preparation_error_probability',
  'source.decoy_intensities',
  'channel.kind',
  'channel.distance_km',
  'channel.depolarizing_probability',
  'channel.phase_damping_probability',
  'detector.kind',
  'detector.efficiency',
  'detector.dark_count_rate_hz',
  'detector.gate_width_s',
  'detector.readout_error_probability',
  'timing.propagation_delay_s',
  'timing.jitter_std_s',
  'timing.clock_offset_s',
  'timing.clock_drift_ppm',
  'post_processing.sifting_enabled',
  'post_processing.qber_abort_threshold',
  'post_processing.qber_sample_fraction',
  'post_processing.error_correction_efficiency',
  'post_processing.reconciliation_block_size',
  'post_processing.privacy_amplification_enabled',
  'post_processing.decoy_security_estimation_enabled',
  'post_processing.decoy_security_method',
  'eavesdropper.kind',
  'eavesdropper.intercept_probability',
  'eavesdropper.pns_split_probability',
  'eavesdropper.pns_block_single_photon_probability',
])

const mediumFields: Record<MediumId, Set<string> | null> = {
  ideal: new Set([
    ...baseFields,
    'detector.double_click_policy',
  ]),
  fiber: new Set([
    ...baseFields,
    'channel.attenuation_db_km',
    'channel.fixed_loss_db',
    'channel.wavelength_nm',
    'channel.pmd_coefficient_ps_sqrt_km',
    'channel.chromatic_dispersion_ps_nm_km',
    'channel.source_spectral_width_nm',
    'channel.polarization_dependent_loss_db',
    'channel.pdl_axis_basis',
    'channel.pdl_axis_bit',
    'channel.classical_channel_power_mw',
    'channel.raman_coefficient_hz_mw_km',
    'channel.raman_filter_isolation_db',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
    'detector.double_click_policy',
  ]),
  vacuum: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.background_count_rate_hz',
  ]),
  air: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.atmospheric_extinction_db_km',
    'channel.scintillation_sigma',
    'channel.pointing_jitter_rad',
    'channel.background_count_rate_hz',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
  ]),
  satellite: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.beam_divergence_rad',
    'channel.atmospheric_extinction_db_km',
    'channel.scintillation_sigma',
    'channel.pointing_jitter_rad',
    'channel.background_count_rate_hz',
  ]),
  underwater: new Set([
    ...baseFields,
    'channel.wavelength_nm',
    'channel.transmitter_aperture_m',
    'channel.receiver_aperture_m',
    'channel.underwater_extinction_m_inv',
    'channel.underwater_scattering_broadening_ns_per_m',
    'channel.background_count_rate_hz',
    'detector.dead_time_s',
    'detector.afterpulse_probability',
  ]),
  custom: null,
}

export function visibleFieldsForMedium({
  fields,
  mediumId,
  scenario,
  expert,
  search,
}: VisibleFieldsArgs): CatalogField[] {
  const query = search.trim().toLowerCase()
  return fields.filter((field) => {
    if (!isCatalogVisible(field, scenario) && query.length === 0) {
      return false
    }
    if (query.length > 0) {
      return matchesSearch(field, query)
    }
    if (expert || mediumId === 'custom') {
      return true
    }
    const allowed = mediumFields[mediumId]
    return allowed === null || allowed.has(field.key)
  })
}

export function isCatalogVisible(
  field: CatalogField,
  scenario: Record<string, unknown>,
): boolean {
  if (!field.visible_when) {
    return true
  }
  return readTarget(scenario, field.visible_when.target) === field.visible_when.equals
}

function matchesSearch(field: CatalogField, query: string): boolean {
  return (
    field.key.toLowerCase().includes(query) ||
    field.label_es.toLowerCase().includes(query)
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/designer/fieldVisibility.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add panel/web/src/features/designer/fieldVisibility.ts panel/web/src/features/designer/fieldVisibility.test.ts
git commit -m "filter dashboard fields by medium"
```

---

### Task 4: Plain-Language Curve Recipes

**Files:**
- Create: `panel/web/src/features/curves/recipes.ts`
- Create: `panel/web/src/features/curves/recipes.test.ts`

- [ ] **Step 1: Write the failing test**

Create `panel/web/src/features/curves/recipes.test.ts`:

```ts
import { expect, test } from 'vitest'

import { buildCurveRequest, curveRecipes, describeCurveRequest } from './recipes'

test('builds a fiber distance sweep from a recipe', () => {
  const request = buildCurveRequest('skr-distance', 'fiber')

  expect(request.axis).toEqual({
    target: 'channel.distance_km',
    values: { start: 0, stop: 120, steps: 25, scale: 'linear' },
  })
  expect(request.metric).toBe('secret_key_rate_bps')
  expect(describeCurveRequest(request)).toBe(
    'Barrido de distancia de fibra de 0 a 120 km en 25 puntos.',
  )
})

test('builds an ideal baseline sweep without medium loss controls', () => {
  const request = buildCurveRequest('ideal-baseline', 'ideal')

  expect(request.axis.target).toBe('scenario.pulses')
  expect(request.axis.values).toEqual({ start: 256, stop: 8192, steps: 8, scale: 'log' })
  expect(request.metric).toBe('qber')
})

test('builds recipe-specific medium sweeps', () => {
  expect(buildCurveRequest('gain-pointing', 'satellite').axis.target).toBe(
    'channel.pointing_jitter_rad',
  )
  expect(buildCurveRequest('gain-water-extinction', 'underwater').axis.target).toBe(
    'channel.underwater_extinction_m_inv',
  )
  expect(buildCurveRequest('qber-atmosphere', 'air').axis.target).toBe(
    'channel.atmospheric_extinction_db_km',
  )
})

test('exposes required one-click recipes', () => {
  expect(curveRecipes.map((recipe) => recipe.id)).toContain('qber-eve')
  expect(curveRecipes.map((recipe) => recipe.id)).toContain('chsh-depolarization')
  expect(curveRecipes.map((recipe) => recipe.id)).toContain('metrics-time')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/curves/recipes.test.ts
```

Expected: FAIL because `recipes.ts` does not exist.

- [ ] **Step 3: Implement curve recipes**

Create `panel/web/src/features/curves/recipes.ts`:

```ts
import type { AxisRequest } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'

export type CurveRecipeId =
  | 'ideal-baseline'
  | 'skr-distance'
  | 'qber-distance'
  | 'qber-dark-counts'
  | 'mean-photon-number'
  | 'qber-eve'
  | 'chsh-depolarization'
  | 'gain-pointing'
  | 'qber-atmosphere'
  | 'gain-water-extinction'
  | 'metrics-time'
  | 'custom-axis'

export type CurveRequest = {
  recipeId: CurveRecipeId
  label: string
  metric: string
  axis: AxisRequest
  series: AxisRequest | null
  repeats: number
}

export type CurveRecipe = {
  id: CurveRecipeId
  label: string
  question: string
  metric: string
  defaultAxis: AxisRequest
  preferredMedia: MediumId[]
}

export const curveRecipes: CurveRecipe[] = [
  recipe('ideal-baseline', 'Baseline ideal', 'Como escala el canal ideal?', 'qber', 'scenario.pulses', 256, 8192, 8, 'log', ['ideal']),
  recipe('skr-distance', 'SKR vs distancia', 'Que pasa si aumenta la distancia?', 'secret_key_rate_bps', 'channel.distance_km', 0, 120, 25, 'linear', ['fiber', 'vacuum', 'air', 'satellite']),
  recipe('qber-distance', 'QBER vs distancia', 'Cuando se acerca al umbral QBER?', 'qber', 'channel.distance_km', 0, 120, 25, 'linear', ['fiber', 'air', 'satellite', 'underwater']),
  recipe('qber-dark-counts', 'QBER vs dark counts', 'Cuanto ruido de detector tolera?', 'qber', 'detector.dark_count_rate_hz', 0, 1000, 21, 'linear', ['ideal', 'fiber', 'air', 'underwater']),
  recipe('mean-photon-number', 'SKR/QBER vs mu', 'Que intensidad debil conviene?', 'gain', 'source.mean_photon_number', 0.01, 0.8, 16, 'linear', ['fiber', 'air', 'satellite', 'underwater']),
  recipe('qber-eve', 'QBER vs Eve', 'Como sube el error con Eve?', 'qber', 'eavesdropper.intercept_probability', 0, 1, 11, 'linear', ['ideal', 'fiber', 'air']),
  recipe('chsh-depolarization', 'CHSH vs despolarizacion', 'Cuando se rompe Bell?', 'chsh_s', 'channel.depolarizing_probability', 0, 0.2, 11, 'linear', ['ideal', 'satellite', 'vacuum']),
  recipe('gain-pointing', 'Gain vs pointing', 'Cuanto afecta el apuntado?', 'gain', 'channel.pointing_jitter_rad', 0, 20e-6, 15, 'linear', ['vacuum', 'air', 'satellite']),
  recipe('qber-atmosphere', 'QBER vs atmosfera', 'Cuanto afecta la extincion del aire?', 'qber', 'channel.atmospheric_extinction_db_km', 0, 3, 13, 'linear', ['air', 'satellite']),
  recipe('gain-water-extinction', 'Gain vs agua', 'Cuanto afecta la extincion del agua?', 'gain', 'channel.underwater_extinction_m_inv', 0.01, 0.2, 16, 'linear', ['underwater']),
  recipe('metrics-time', 'Metricas vs tiempo', 'Como evoluciona la dinamica temporal?', 'qber', 'time_s', 0, 0.001, 8, 'linear', ['ideal', 'fiber', 'vacuum', 'air', 'satellite', 'underwater', 'custom']),
  recipe('custom-axis', 'Barrido custom', 'Que parametro quieres barrer?', 'qber', 'channel.distance_km', 0, 100, 16, 'linear', ['custom']),
]

export function buildCurveRequest(
  recipeId: CurveRecipeId,
  mediumId: MediumId,
): CurveRequest {
  const recipe = curveRecipes.find((item) => item.id === recipeId) ?? curveRecipes[0]
  const axis =
    recipe.id === 'skr-distance' && mediumId === 'underwater'
      ? axis('channel.distance_km', 0.001, 0.05, 20, 'linear')
      : recipe.defaultAxis
  return {
    recipeId: recipe.id,
    label: recipe.label,
    metric: recipe.metric,
    axis,
    series: null,
    repeats: 1,
  }
}

export function describeCurveRequest(request: CurveRequest): string {
  const values = request.axis.values
  if (Array.isArray(values)) {
    return `Barrido de ${humanTarget(request.axis.target)} con ${values.length} valores.`
  }
  return `Barrido de ${humanTarget(request.axis.target)} de ${values.start} a ${values.stop}${unitForTarget(request.axis.target)} en ${values.steps} puntos.`
}

function recipe(
  id: CurveRecipeId,
  label: string,
  question: string,
  metric: string,
  target: string,
  start: number,
  stop: number,
  steps: number,
  scale: 'linear' | 'log',
  preferredMedia: MediumId[],
): CurveRecipe {
  return {
    id,
    label,
    question,
    metric,
    defaultAxis: axis(target, start, stop, steps, scale),
    preferredMedia,
  }
}

function axis(
  target: string,
  start: number,
  stop: number,
  steps: number,
  scale: 'linear' | 'log',
): AxisRequest {
  return { target, values: { start, stop, steps, scale } }
}

function humanTarget(target: string): string {
  const labels: Record<string, string> = {
    'scenario.pulses': 'pulsos',
    'channel.distance_km': 'distancia de fibra',
    'channel.pointing_jitter_rad': 'jitter de apuntado',
    'channel.underwater_extinction_m_inv': 'extincion del agua',
    'channel.atmospheric_extinction_db_km': 'extincion atmosferica',
    'detector.dark_count_rate_hz': 'dark counts',
    'source.mean_photon_number': 'mu',
    'eavesdropper.intercept_probability': 'fuerza de Eve',
    'channel.depolarizing_probability': 'despolarizacion',
    time_s: 'tiempo',
  }
  return labels[target] ?? target
}

function unitForTarget(target: string): string {
  if (target.endsWith('_km')) {
    return ' km'
  }
  if (target.endsWith('_rad')) {
    return ' rad'
  }
  if (target.endsWith('_hz')) {
    return ' Hz'
  }
  return ''
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/curves/recipes.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add panel/web/src/features/curves/recipes.ts panel/web/src/features/curves/recipes.test.ts
git commit -m "add guided curve recipes"
```

---

### Task 5: Simple Temporal Pattern Builder

**Files:**
- Create: `panel/web/src/features/dynamics/temporalPatterns.ts`
- Create: `panel/web/src/features/dynamics/temporalPatterns.test.ts`

- [ ] **Step 1: Write the failing test**

Create `panel/web/src/features/dynamics/temporalPatterns.test.ts`:

```ts
import { expect, test } from 'vitest'

import { buildTemporalSchedule, temporalPatternOptions } from './temporalPatterns'

test('builds a stable-link constant schedule', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'stable',
    phenomenon: 'loss',
    severity: 'mild',
    duration: 'short',
    direction: 'increasing',
    currentValue: 2,
  })

  expect(schedule).toEqual({
    target: 'channel.fixed_loss_db',
    profile: { kind: 'constant', start_s: 0, end_s: 0.001, value: 2 },
  })
})

test('builds gradual QBER-driving degradation', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'degradation',
    phenomenon: 'error',
    severity: 'moderate',
    duration: 'medium',
    direction: 'increasing',
    currentValue: 0.01,
  })

  expect(schedule.target).toBe('channel.depolarizing_probability')
  expect(schedule.profile).toEqual({
    kind: 'linear',
    start_s: 0,
    end_s: 0.01,
    start_value: 0.01,
    end_value: 0.06,
  })
})

test('builds recovery by decreasing the selected phenomenon', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'recovery',
    phenomenon: 'background',
    severity: 'severe',
    duration: 'long',
    direction: 'decreasing',
    currentValue: 500,
  })

  expect(schedule.target).toBe('channel.background_count_rate_hz')
  expect(schedule.profile).toEqual({
    kind: 'linear',
    start_s: 0,
    end_s: 0.1,
    start_value: 500,
    end_value: 250,
  })
})

test('builds burst as a finite constant spike', () => {
  const schedule = buildTemporalSchedule({
    pattern: 'burst',
    phenomenon: 'timing',
    severity: 'mild',
    duration: 'short',
    direction: 'spike',
    currentValue: 0,
  })

  expect(schedule.target).toBe('timing.clock_offset_s')
  expect(schedule.profile).toEqual({
    kind: 'constant',
    start_s: 0.00025,
    end_s: 0.0005,
    value: 1e-10,
  })
})

test('exposes the required named patterns', () => {
  expect(temporalPatternOptions.map((item) => item.id)).toEqual([
    'stable',
    'degradation',
    'recovery',
    'drift',
    'burst',
  ])
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/dynamics/temporalPatterns.test.ts
```

Expected: FAIL because `temporalPatterns.ts` does not exist.

- [ ] **Step 3: Implement temporal patterns**

Create `panel/web/src/features/dynamics/temporalPatterns.ts`:

```ts
export type TemporalPatternId = 'stable' | 'degradation' | 'recovery' | 'drift' | 'burst'
export type TemporalPhenomenon = 'loss' | 'error' | 'alignment' | 'background' | 'timing' | 'eve'
export type TemporalSeverity = 'mild' | 'moderate' | 'severe'
export type TemporalDuration = 'short' | 'medium' | 'long'
export type TemporalDirection = 'increasing' | 'decreasing' | 'spike'

export type TemporalPatternRequest = {
  pattern: TemporalPatternId
  phenomenon: TemporalPhenomenon
  severity: TemporalSeverity
  duration: TemporalDuration
  direction: TemporalDirection
  currentValue: number
}

export type TemporalSchedule = {
  target: string
  profile:
    | { kind: 'constant'; start_s: number; end_s: number; value: number }
    | { kind: 'linear'; start_s: number; end_s: number; start_value: number; end_value: number }
}

export const temporalPatternOptions = [
  { id: 'stable' as const, label: 'Enlace estable' },
  { id: 'degradation' as const, label: 'Degradacion gradual' },
  { id: 'recovery' as const, label: 'Recuperacion' },
  { id: 'drift' as const, label: 'Drift' },
  { id: 'burst' as const, label: 'Evento de ruido' },
]

const targets: Record<TemporalPhenomenon, string> = {
  loss: 'channel.fixed_loss_db',
  error: 'channel.depolarizing_probability',
  alignment: 'channel.polarization_rotation_y_rad',
  background: 'channel.background_count_rate_hz',
  timing: 'timing.clock_offset_s',
  eve: 'eavesdropper.intercept_probability',
}

const durations: Record<TemporalDuration, number> = {
  short: 0.001,
  medium: 0.01,
  long: 0.1,
}

const deltas: Record<TemporalPhenomenon, Record<TemporalSeverity, number>> = {
  loss: { mild: 1, moderate: 3, severe: 8 },
  error: { mild: 0.01, moderate: 0.05, severe: 0.1 },
  alignment: { mild: 0.01, moderate: 0.05, severe: 0.1 },
  background: { mild: 50, moderate: 200, severe: 500 },
  timing: { mild: 1e-10, moderate: 5e-10, severe: 1e-9 },
  eve: { mild: 0.05, moderate: 0.2, severe: 0.5 },
}

export function buildTemporalSchedule(request: TemporalPatternRequest): TemporalSchedule {
  const target = targets[request.phenomenon]
  const duration = durations[request.duration]
  const delta = deltas[request.phenomenon][request.severity]

  if (request.pattern === 'stable') {
    return {
      target,
      profile: {
        kind: 'constant',
        start_s: 0,
        end_s: duration,
        value: request.currentValue,
      },
    }
  }

  if (request.pattern === 'burst') {
    return {
      target,
      profile: {
        kind: 'constant',
        start_s: duration / 4,
        end_s: duration / 2,
        value: clampValue(request.phenomenon, request.currentValue + delta),
      },
    }
  }

  const sign =
    request.pattern === 'recovery' || request.direction === 'decreasing' ? -1 : 1
  const endValue = clampValue(request.phenomenon, request.currentValue + sign * delta)

  return {
    target,
    profile: {
      kind: 'linear',
      start_s: 0,
      end_s: duration,
      start_value: request.currentValue,
      end_value: endValue,
    },
  }
}

export function describeTemporalSchedule(schedule: TemporalSchedule): string {
  if (schedule.profile.kind === 'constant') {
    return `${schedule.target} queda en ${schedule.profile.value} entre ${schedule.profile.start_s}s y ${schedule.profile.end_s}s.`
  }
  return `${schedule.target} cambia de ${schedule.profile.start_value} a ${schedule.profile.end_value} entre ${schedule.profile.start_s}s y ${schedule.profile.end_s}s.`
}

function clampValue(phenomenon: TemporalPhenomenon, value: number): number {
  if (phenomenon === 'error' || phenomenon === 'eve') {
    return Math.min(1, Math.max(0, value))
  }
  return Math.max(0, value)
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/dynamics/temporalPatterns.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add panel/web/src/features/dynamics/temporalPatterns.ts panel/web/src/features/dynamics/temporalPatterns.test.ts
git commit -m "add simple temporal pattern builder"
```

---

### Task 6: Store Active Medium In Designer State

**Files:**
- Modify: `panel/web/src/features/designer/scenarioStore.ts`
- Create: `panel/web/src/features/designer/scenarioStore.test.ts`

- [ ] **Step 1: Write the failing test**

Create `panel/web/src/features/designer/scenarioStore.test.ts`:

```ts
import { expect, test } from 'vitest'

import { useDesignerStore } from './scenarioStore'

test('loads a scenario and infers the active medium', () => {
  useDesignerStore.getState().loadScenario({
    schema_version: 1,
    channel: { kind: 'underwater' },
    metadata: {},
  })

  expect(useDesignerStore.getState().activeMediumId).toBe('underwater')
})

test('selects a medium and loads its scenario defaults', () => {
  useDesignerStore.getState().selectMedium('ideal')

  expect(useDesignerStore.getState().activeMediumId).toBe('ideal')
  expect(useDesignerStore.getState().scenario.channel).toMatchObject({ kind: 'ideal' })
  expect(useDesignerStore.getState().scenario.metadata).toMatchObject({ mediumId: 'ideal' })
})

test('updating channel kind to custom keeps explicit custom mode', () => {
  useDesignerStore.getState().selectMedium('custom')
  useDesignerStore.getState().updateField('channel.kind', 'fiber')

  expect(useDesignerStore.getState().activeMediumId).toBe('custom')
  expect(useDesignerStore.getState().scenario.channel).toMatchObject({ kind: 'fiber' })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/designer/scenarioStore.test.ts
```

Expected: FAIL because `activeMediumId` and `selectMedium` do not exist.

- [ ] **Step 3: Modify the store**

Replace the imports, type, and store body in `panel/web/src/features/designer/scenarioStore.ts` with this shape:

```ts
import { create } from 'zustand'

import type { ScenarioPayload } from '@/api/client'
import { defaultScenario } from '@/features/designer/defaultScenario'
import {
  inferMediumFromScenario,
  scenarioForMedium,
  type MediumId,
} from '@/features/lab/mediums'
import { writeTarget } from '@/features/shared/scenarioPaths'

type DesignerState = {
  scenario: ScenarioPayload
  activeMediumId: MediumId
  loadScenario: (scenario: ScenarioPayload) => void
  selectMedium: (mediumId: MediumId) => void
  updateField: (target: string, value: unknown) => void
}
```

Then replace the `useDesignerStore` initialization and delete the old local `updateScenario` and `isRecord` helpers:

```ts
export const useDesignerStore = create<DesignerState>((set) => ({
  scenario: defaultScenario,
  activeMediumId: inferMediumFromScenario(defaultScenario),
  loadScenario: (scenario) =>
    set({
      scenario,
      activeMediumId: inferMediumFromScenario(scenario),
    }),
  selectMedium: (mediumId) =>
    set({
      scenario: scenarioForMedium(mediumId),
      activeMediumId: mediumId,
    }),
  updateField: (target, value) =>
    set((state) => ({
      scenario: writeTarget(state.scenario, target, value),
      activeMediumId: state.activeMediumId,
    })),
}))
```

- [ ] **Step 4: Run the test to verify it passes**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/designer/scenarioStore.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run the earlier medium tests for store integration**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/lab/mediums.test.ts src/features/designer/scenarioStore.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add panel/web/src/features/designer/scenarioStore.ts panel/web/src/features/designer/scenarioStore.test.ts
git commit -m "track active dashboard medium"
```

---

### Task 7: Gallery, Cockpit, Inspector, Curve, And Temporal UI Components

**Files:**
- Create: `panel/web/src/features/lab/MediumGallery.tsx`
- Create: `panel/web/src/features/lab/LinkCockpit.tsx`
- Create: `panel/web/src/features/designer/FocusedInspector.tsx`
- Create: `panel/web/src/features/curves/CurveRecipeBar.tsx`
- Create: `panel/web/src/features/dynamics/TemporalPatternBuilder.tsx`
- Modify: `panel/web/src/App.tsx`

- [ ] **Step 1: Write failing component tests in `App.test.tsx`**

Replace the old smoke assertions after `render(<App />)` with these expectations:

```ts
expect(await screen.findByText('Laboratorio')).toBeTruthy()
expect(await screen.findByText('Canal ideal')).toBeTruthy()
expect(await screen.findByText('Fibra telecom')).toBeTruthy()
expect(await screen.findByText('Submarino')).toBeTruthy()
expect(screen.queryByText('channel.distance_km')).toBeNull()
```

Add a second test in the same file:

```ts
test('selects fiber and shows cockpit plus focused controls', async () => {
  vi.stubGlobal('fetch', mockPanelFetch())

  render(<App />)

  const fiber = await screen.findByRole('button', { name: /abrir fibra/i })
  fiber.click()

  expect(await screen.findByText('Fuente')).toBeTruthy()
  expect(await screen.findByText('Medio')).toBeTruthy()
  expect(await screen.findByText('Detector')).toBeTruthy()
  expect(await screen.findByText('Inspector granular')).toBeTruthy()
  expect(await screen.findByText('Distancia')).toBeTruthy()
  expect(screen.queryByText('pointing_jitter_rad')).toBeNull()
})
```

Move the current fetch stub body into a reusable helper named `mockPanelFetch()` in `App.test.tsx`:

```ts
function mockPanelFetch(): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => {
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
              field('channel.kind', 'Familia', 'select', 'fiber'),
              field('channel.distance_km', 'Distancia', 'number', 0, 'km'),
              field('channel.pointing_jitter_rad', 'pointing_jitter_rad', 'number', 0, 'rad'),
              field('channel.underwater_extinction_m_inv', 'underwater_extinction_m_inv', 'number', 0),
            ],
          },
        ],
        metrics: [{ key: 'qber', label_es: 'qber', unit: null }],
      })
    }
    if (url === '/api/scenarios/validate') {
      return jsonResponse({ valid: true, digest: 'abcd1234ef' })
    }
    if (url.startsWith('/api/characterize/')) {
      return jsonResponse({
        section: url.split('/').at(-1),
        state: { loss_db: 3.2, transmittance: 0.48, p_dark_per_gate: 0.000001 },
      })
    }
    if (url === '/api/dynamics/preview') {
      return jsonResponse({ rows: [{ time_s: 0, 'channel.distance_km': 0 }] })
    }
    throw new Error(`Unexpected URL: ${url}`)
  }) as typeof fetch
}

function field(
  key: string,
  label: string,
  type: string,
  defaultValue: unknown,
  unit: string | null = null,
) {
  return {
    key,
    label_es: label,
    type,
    unit,
    default: defaultValue,
    sweepable: true,
  }
}
```

- [ ] **Step 2: Run the app test to verify it fails**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/App.test.tsx
```

Expected: FAIL because the first screen is still `Disenador` and the new components do not exist.

- [ ] **Step 3: Create `MediumGallery.tsx`**

Create `panel/web/src/features/lab/MediumGallery.tsx`:

```tsx
import {
  Cable,
  CloudSun,
  Orbit,
  Satellite,
  SlidersHorizontal,
  Sparkles,
  Waves,
} from 'lucide-react'

import type { MediumDefinition, MediumId } from './mediums'

type MediumGalleryProps = {
  media: MediumDefinition[]
  activeMediumId: MediumId
  onOpen: (mediumId: MediumId) => void
}

const icons = {
  sparkles: Sparkles,
  cable: Cable,
  orbit: Orbit,
  cloud: CloudSun,
  satellite: Satellite,
  waves: Waves,
  sliders: SlidersHorizontal,
}

export function MediumGallery({ media, activeMediumId, onOpen }: MediumGalleryProps) {
  return (
    <section className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      {media.map((medium) => {
        const Icon = icons[medium.icon]
        const active = activeMediumId === medium.id
        return (
          <article
            className={`rounded border bg-surface p-4 ${active ? medium.accentClass : 'border-border'}`}
            key={medium.id}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-normal text-slate-500">
                  {medium.realismLabel}
                </p>
                <h2 className="mt-1 text-lg font-semibold text-white">{medium.label}</h2>
              </div>
              <Icon aria-hidden="true" className="text-current" size={22} />
            </div>
            <p className="mt-3 min-h-12 text-sm text-slate-300">{medium.summary}</p>
            <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded border border-border bg-background/60 p-2">
                <dt className="text-slate-500">Rango</dt>
                <dd className="mt-1 font-mono text-slate-200">{medium.expectedRange}</dd>
              </div>
              <div className="rounded border border-border bg-background/60 p-2">
                <dt className="text-slate-500">Detector</dt>
                <dd className="mt-1 font-mono text-slate-200">{medium.detectorLabel}</dd>
              </div>
            </dl>
            <button
              aria-label={`Abrir ${medium.shortLabel}`}
              className="mt-4 flex h-9 w-full items-center justify-center rounded border border-cyan px-3 text-sm text-cyan hover:bg-cyan/10"
              onClick={() => onOpen(medium.id)}
              type="button"
            >
              Abrir
            </button>
          </article>
        )
      })}
    </section>
  )
}
```

- [ ] **Step 4: Create `LinkCockpit.tsx`**

Create `panel/web/src/features/lab/LinkCockpit.tsx`:

```tsx
import { ArrowRight, Play, Save } from 'lucide-react'

import type { MediumDefinition } from './mediums'

type LinkCockpitProps = {
  medium: MediumDefinition
  channelState: Record<string, unknown>
  sourceState: Record<string, unknown>
  detectorState: Record<string, unknown>
  timingState: Record<string, unknown>
  onRun: () => void
  onSave: () => void
}

export function LinkCockpit({
  medium,
  channelState,
  sourceState,
  detectorState,
  timingState,
  onRun,
  onSave,
}: LinkCockpitProps) {
  return (
    <section className="space-y-4">
      <div className="rounded border border-border bg-surface p-4">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]">
          <Node label="Fuente" value={formatMetric(sourceState.mean_photon_rate_hz, ' fot/s')} />
          <Arrow />
          <Node label="Medio" value={medium.shortLabel} accent={medium.accentClass} />
          <Arrow />
          <Node label="Detector" value={formatMetric(detectorState.p_dark_per_gate)} />
          <Arrow />
          <Node label="Post-proceso" value={formatMetric(timingState.effective_jitter_std_s, ' s')} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Metric label="loss" value={formatMetric(channelState.loss_db, ' dB')} />
          <Metric label="eta" value={formatMetric(channelState.transmittance)} />
          <Metric label="p_dark" value={formatMetric(detectorState.p_dark_per_gate)} />
          <Metric label="sigma" value={formatMetric(timingState.effective_jitter_std_s, ' s')} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            className="flex h-9 items-center gap-2 rounded border border-cyan px-3 text-sm text-cyan hover:bg-cyan/10"
            onClick={onRun}
            type="button"
          >
            <Play size={15} aria-hidden="true" />
            Ejecutar
          </button>
          <button
            className="flex h-9 items-center gap-2 rounded border border-success px-3 text-sm text-success hover:bg-success/10"
            onClick={onSave}
            type="button"
          >
            <Save size={15} aria-hidden="true" />
            Guardar
          </button>
        </div>
      </div>
    </section>
  )
}

function Node({
  label,
  value,
  accent = 'border-border',
}: {
  label: string
  value: string
  accent?: string
}) {
  return (
    <div className={`rounded border bg-background/60 p-3 ${accent}`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-2 min-h-6 text-sm font-semibold text-white">{value}</p>
    </div>
  )
}

function Arrow() {
  return (
    <div className="hidden items-center justify-center text-slate-500 lg:flex">
      <ArrowRight size={18} aria-hidden="true" />
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-border bg-background/60 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-2 font-mono text-base text-white">{value}</p>
    </div>
  )
}

function formatMetric(value: unknown, suffix = ''): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '...'
  }
  return `${value.toFixed(value === 0 ? 0 : value < 0.01 ? 6 : 2)}${suffix}`
}
```

- [ ] **Step 5: Create `FocusedInspector.tsx`**

Create `panel/web/src/features/designer/FocusedInspector.tsx` by moving the existing `SchemaForm`, `SchemaField`, `FieldControl`, `NumberOrTextInput`, `ListInput`, `JsonEditor`, `DecoyTable`, `MiniNumberInput`, and their direct formatting helpers from `App.tsx`. Add these props to the exported component:

```tsx
export function FocusedInspector({
  errors,
  sections,
  scenario,
  mediumId,
  onChange,
}: {
  errors: ApiValidationIssue[]
  sections: CatalogSection[]
  scenario: Record<string, unknown>
  mediumId: MediumId
  onChange: (target: string, value: unknown) => void
}) {
  const [search, setSearch] = useState('')
  const [expert, setExpert] = useState(false)
  return (
    <section className="rounded border border-border bg-surface">
      <div className="flex flex-col gap-3 border-b border-border p-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Inspector granular</h2>
          <p className="mt-1 text-xs text-slate-500">
            Filtrado por medio, con modo experto para ver todo.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            className="h-9 rounded border border-border bg-background px-3 text-sm text-white outline-none focus:border-cyan"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar parametro"
            value={search}
          />
          <label className="flex h-9 items-center gap-2 rounded border border-border px-3 text-sm text-slate-300">
            <input
              checked={expert}
              className="accent-cyan"
              onChange={(event) => setExpert(event.target.checked)}
              type="checkbox"
            />
            Expert: todo
          </label>
        </div>
      </div>
      <div className="space-y-4 p-4">
        {sections
          .filter((section) => section.key !== 'dynamic')
          .map((section) => {
            const visibleFields = visibleFieldsForMedium({
              fields: section.fields,
              mediumId,
              scenario,
              expert,
              search,
            })
            if (visibleFields.length === 0) {
              return null
            }
            return (
              <section className="border-b border-border pb-4 last:border-b-0 last:pb-0" key={section.key}>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white">{section.label_es}</h3>
                  <span className="font-mono text-xs text-slate-500">{visibleFields.length}</span>
                </div>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  {visibleFields.map((field) => (
                    <SchemaField
                      error={fieldError(errors, field.key)}
                      field={field}
                      key={field.key}
                      onChange={onChange}
                      value={readTarget(scenario, field.key) ?? field.default}
                    />
                  ))}
                </div>
              </section>
            )
          })}
      </div>
    </section>
  )
}
```

Import these dependencies at the top:

```tsx
import { CheckCircle2, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

import type { ApiValidationIssue, CatalogField, CatalogSection } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'
import { readTarget } from '@/features/shared/scenarioPaths'
import { visibleFieldsForMedium } from './fieldVisibility'
```

- [ ] **Step 6: Create `CurveRecipeBar.tsx`**

Create `panel/web/src/features/curves/CurveRecipeBar.tsx`:

```tsx
import { SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'

import type { AxisRequest } from '@/api/client'
import type { MediumId } from '@/features/lab/mediums'
import {
  buildCurveRequest,
  curveRecipes,
  describeCurveRequest,
  type CurveRecipeId,
  type CurveRequest,
} from './recipes'

type CurveRecipeBarProps = {
  mediumId: MediumId
  activeRecipeId: CurveRecipeId
  onChange: (request: CurveRequest) => void
}

export function CurveRecipeBar({
  mediumId,
  activeRecipeId,
  onChange,
}: CurveRecipeBarProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const request = buildCurveRequest(activeRecipeId, mediumId)
  const relevantRecipes = curveRecipes.filter(
    (recipe) => recipe.preferredMedia.includes(mediumId) || mediumId === 'custom',
  )

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Curvas faciles</h2>
          <p className="mt-1 text-xs text-slate-500">{describeCurveRequest(request)}</p>
        </div>
        <button
          className="flex h-9 items-center gap-2 rounded border border-border px-3 text-sm text-slate-300 hover:text-white"
          onClick={() => setAdvancedOpen((value) => !value)}
          type="button"
        >
          <SlidersHorizontal size={15} aria-hidden="true" />
          Avanzado
        </button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {relevantRecipes.map((recipe) => (
          <button
            className={`rounded border px-3 py-2 text-left text-xs ${
              recipe.id === activeRecipeId
                ? 'border-cyan bg-cyan/10 text-cyan'
                : 'border-border text-slate-300 hover:text-white'
            }`}
            key={recipe.id}
            onClick={() => onChange(buildCurveRequest(recipe.id, mediumId))}
            type="button"
          >
            <span className="block font-medium">{recipe.label}</span>
            <span className="mt-1 block text-slate-500">{recipe.question}</span>
          </button>
        ))}
      </div>
      {advancedOpen ? <AdvancedAxis axis={request.axis} metric={request.metric} /> : null}
    </section>
  )
}

function AdvancedAxis({ axis, metric }: { axis: AxisRequest; metric: string }) {
  return (
    <div className="mt-3 rounded border border-border bg-background/60 p-3 font-mono text-xs text-slate-300">
      <div>metric: {metric}</div>
      <div>axis: {axis.target}</div>
      <div>values: {JSON.stringify(axis.values)}</div>
    </div>
  )
}
```

- [ ] **Step 7: Create `TemporalPatternBuilder.tsx`**

Create `panel/web/src/features/dynamics/TemporalPatternBuilder.tsx`:

```tsx
import { useMemo, useState } from 'react'

import { readTarget } from '@/features/shared/scenarioPaths'
import {
  buildTemporalSchedule,
  describeTemporalSchedule,
  temporalPatternOptions,
  type TemporalDirection,
  type TemporalDuration,
  type TemporalPhenomenon,
  type TemporalSeverity,
} from './temporalPatterns'

type TemporalPatternBuilderProps = {
  scenario: Record<string, unknown>
  onChange: (target: string, value: unknown) => void
}

export function TemporalPatternBuilder({
  scenario,
  onChange,
}: TemporalPatternBuilderProps) {
  const [pattern, setPattern] = useState('stable')
  const [phenomenon, setPhenomenon] = useState<TemporalPhenomenon>('error')
  const [severity, setSeverity] = useState<TemporalSeverity>('moderate')
  const [duration, setDuration] = useState<TemporalDuration>('medium')
  const [direction, setDirection] = useState<TemporalDirection>('increasing')
  const currentValue = Number(readTarget(scenario, phenomenonTarget(phenomenon)) ?? 0)
  const schedule = useMemo(
    () =>
      buildTemporalSchedule({
        pattern: pattern as Parameters<typeof buildTemporalSchedule>[0]['pattern'],
        phenomenon,
        severity,
        duration,
        direction,
        currentValue,
      }),
    [currentValue, direction, duration, pattern, phenomenon, severity],
  )

  return (
    <section className="rounded border border-border bg-surface p-4">
      <div>
        <h2 className="text-sm font-semibold text-white">Temporalidad simple</h2>
        <p className="mt-1 text-xs text-slate-500">{describeTemporalSchedule(schedule)}</p>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-5">
        <Select label="modo" onChange={setPattern} options={temporalPatternOptions.map((item) => item.id)} value={pattern} />
        <Select label="fenomeno" onChange={(value) => setPhenomenon(value as TemporalPhenomenon)} options={['loss', 'error', 'alignment', 'background', 'timing', 'eve']} value={phenomenon} />
        <Select label="severidad" onChange={(value) => setSeverity(value as TemporalSeverity)} options={['mild', 'moderate', 'severe']} value={severity} />
        <Select label="duracion" onChange={(value) => setDuration(value as TemporalDuration)} options={['short', 'medium', 'long']} value={duration} />
        <Select label="direccion" onChange={(value) => setDirection(value as TemporalDirection)} options={['increasing', 'decreasing', 'spike']} value={direction} />
      </div>
      <button
        className="mt-4 rounded border border-cyan px-3 py-2 text-sm text-cyan hover:bg-cyan/10"
        onClick={() => onChange('dynamic.parameter_schedules', [schedule])}
        type="button"
      >
        Aplicar patron temporal
      </button>
    </section>
  )
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (value: string) => void
}) {
  return (
    <label className="block">
      <span className="text-xs text-slate-500">{label}</span>
      <select
        className="mt-1 h-9 w-full rounded border border-border bg-background px-2 text-xs text-white outline-none focus:border-cyan"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  )
}

function phenomenonTarget(phenomenon: TemporalPhenomenon): string {
  const targets: Record<TemporalPhenomenon, string> = {
    loss: 'channel.fixed_loss_db',
    error: 'channel.depolarizing_probability',
    alignment: 'channel.polarization_rotation_y_rad',
    background: 'channel.background_count_rate_hz',
    timing: 'timing.clock_offset_s',
    eve: 'eavesdropper.intercept_probability',
  }
  return targets[phenomenon]
}
```

- [ ] **Step 8: Wire components in `App.tsx`**

Modify imports:

```tsx
import { CurveRecipeBar } from './features/curves/CurveRecipeBar'
import type { CurveRecipeId, CurveRequest } from './features/curves/recipes'
import { TemporalPatternBuilder } from './features/dynamics/TemporalPatternBuilder'
import { FocusedInspector } from './features/designer/FocusedInspector'
import { LinkCockpit } from './features/lab/LinkCockpit'
import { MediumGallery } from './features/lab/MediumGallery'
import { mediumDefinitions, mediumOptions } from './features/lab/mediums'
```

In `PanelShell`, read the new store state:

```tsx
const activeMediumId = useDesignerStore((state) => state.activeMediumId)
const selectMedium = useDesignerStore((state) => state.selectMedium)
const [activeCurveRequest, setActiveCurveRequest] = useState<CurveRequest | null>(null)
const activeMedium = mediumDefinitions[activeMediumId]
```

Change the initial active view type and nav:

```tsx
type ActiveView = 'lab' | 'curves' | 'results' | 'library'
const [activeView, setActiveView] = useState<ActiveView>('lab')
const navItems = [
  { id: 'lab' as const, label: 'Laboratorio', Icon: FlaskConical },
  { id: 'curves' as const, label: 'Curvas', Icon: Gauge },
  { id: 'results' as const, label: 'Ejecucion', Icon: Activity },
  { id: 'library' as const, label: 'Biblioteca', Icon: Library },
]
```

Render `Laboratorio` as the first view:

```tsx
{activeView === 'lab' ? (
  <div className="space-y-5">
    <MediumGallery
      activeMediumId={activeMediumId}
      media={mediumOptions}
      onOpen={(mediumId) => {
        selectMedium(mediumId)
        setActiveCurveRequest(null)
      }}
    />
    <LinkCockpit
      channelState={channelState}
      detectorState={detectorState}
      medium={activeMedium}
      onRun={() => setActiveView('results')}
      onSave={() => setActiveView('library')}
      sourceState={sourceState}
      timingState={timingState}
    />
    <CurveRecipeBar
      activeRecipeId={(activeCurveRequest?.recipeId ?? activeMedium.defaultCurveRecipeId) as CurveRecipeId}
      mediumId={activeMediumId}
      onChange={setActiveCurveRequest}
    />
    <TemporalPatternBuilder scenario={scenario} onChange={updateField} />
    {validationIssues.length > 0 ? <ValidationSummary issues={validationIssues} /> : null}
    <FocusedInspector
      errors={validationIssues}
      mediumId={activeMediumId}
      onChange={updateField}
      scenario={scenario}
      sections={catalogSections}
    />
  </div>
) : activeView === 'library' ? (
  <LibraryView
    currentScenario={scenario}
    onLoad={(nextScenario) => {
      loadScenario(nextScenario)
      setActiveView('lab')
    }}
  />
) : activeView === 'results' ? (
  <ExecutionView scenario={scenario} />
) : (
  <CurvesView
    initialRequest={activeCurveRequest}
    metrics={catalog.data?.metrics ?? []}
    scenario={scenario}
    sweepableFields={sweepableFields}
  />
)}
```

After `FocusedInspector` is imported, remove the old inline `SchemaForm` call from the lab path. Keep the old component definitions in `App.tsx` until the extraction is verified, then delete only the definitions that moved to `FocusedInspector.tsx`.

- [ ] **Step 9: Run the app test**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/App.test.tsx
```

Expected: PASS.

- [ ] **Step 10: Run all frontend unit tests**

Run from `panel/web`:

```powershell
npm.cmd test -- --run
```

Expected: PASS.

- [ ] **Step 11: Commit**

```powershell
git add panel/web/src/App.tsx panel/web/src/App.test.tsx panel/web/src/features/lab/MediumGallery.tsx panel/web/src/features/lab/LinkCockpit.tsx panel/web/src/features/designer/FocusedInspector.tsx panel/web/src/features/curves/CurveRecipeBar.tsx panel/web/src/features/dynamics/TemporalPatternBuilder.tsx
git commit -m "add medium-first lab dashboard"
```

---

### Task 8: Curve Workbench Uses Recipe Requests

**Files:**
- Modify: `panel/web/src/App.tsx`
- Modify or create: `panel/web/src/features/curves/CurveWorkbench.tsx`

- [ ] **Step 1: Write the failing test**

Add this test to `panel/web/src/features/curves/recipes.test.ts`:

```ts
test('serializes recipe request into sweep body fields', () => {
  const request = buildCurveRequest('qber-eve', 'fiber')

  expect(request.axis).toEqual({
    target: 'eavesdropper.intercept_probability',
    values: { start: 0, stop: 1, steps: 11, scale: 'linear' },
  })
  expect(request.repeats).toBe(1)
  expect(request.series).toBeNull()
})
```

- [ ] **Step 2: Run the test**

Run from `panel/web`:

```powershell
npm.cmd test -- --run src/features/curves/recipes.test.ts
```

Expected: PASS. This confirms the existing recipe model already carries the needed sweep body.

- [ ] **Step 3: Modify `CurvesView` props**

In `panel/web/src/App.tsx`, update `CurvesView` props:

```tsx
function CurvesView({
  initialRequest,
  metrics,
  scenario,
  sweepableFields,
}: {
  initialRequest: CurveRequest | null
  metrics: Array<{ key: string; label_es: string; unit: string | null }>
  scenario: Record<string, unknown>
  sweepableFields: CatalogField[]
}) {
```

Initialize state from `initialRequest`:

```tsx
const initialAxis = initialRequest?.axis
const initialValues = !Array.isArray(initialAxis?.values) ? initialAxis?.values : null
const [axisTarget, setAxisTarget] = useState(initialAxis?.target ?? 'channel.distance_km')
const [metric, setMetric] = useState(initialRequest?.metric ?? 'secret_key_rate_bps')
const [start, setStart] = useState(Number(initialValues?.start ?? 0))
const [stop, setStop] = useState(Number(initialValues?.stop ?? 120))
const [steps, setSteps] = useState(Number(initialValues?.steps ?? 5))
const [repeats, setRepeats] = useState(initialRequest?.repeats ?? 1)
const [scale, setScale] = useState<'linear' | 'log'>(initialValues?.scale ?? 'linear')
```

Add a small readable sentence above the advanced controls:

```tsx
{initialRequest ? (
  <p className="mb-3 text-sm text-slate-300">
    Receta activa: {initialRequest.label}
  </p>
) : null}
```

- [ ] **Step 4: Run frontend tests**

Run from `panel/web`:

```powershell
npm.cmd test -- --run
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add panel/web/src/App.tsx panel/web/src/features/curves/recipes.test.ts
git commit -m "connect curve recipes to sweep workbench"
```

---

### Task 9: Backend Preset Surface Includes Ideal And Realistic Media

**Files:**
- Modify: `panel/api/runtime.py`
- Modify: `tests/panel_api/test_phase2.py`

- [ ] **Step 1: Inspect current preset diff**

Run:

```powershell
git diff -- panel/api/runtime.py tests/panel_api/test_phase2.py
```

Expected: shows existing local preset changes. Keep them and extend them.

- [ ] **Step 2: Write or update the failing backend test**

In `tests/panel_api/test_phase2.py`, update the preset test to assert these names:

```py
def test_presets_returns_medium_first_scenarios(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/api/presets")

    assert response.status_code == 200
    presets = response.json()["presets"]
    names = {preset["name"] for preset in presets}
    assert {
        "Canal ideal",
        "Fibra metropolitana (Ideal)",
        "Satélite LEO (Ideal)",
        "PNS sobre decoy débil",
        "E91 con scintillation",
        "Telecom Fibra 100 km (SNSPD Real)",
        "Free Space Urbano 1.5 km (SPAD Real)",
        "Enlace Submarino 30 m (Real)",
    }.issubset(names)
    by_name = {preset["name"]: preset for preset in presets}
    assert by_name["Canal ideal"]["scenario"]["channel"]["kind"] == "ideal"
    assert by_name["Telecom Fibra 100 km (SNSPD Real)"]["scenario"]["channel"]["kind"] == "fiber"
    assert by_name["Free Space Urbano 1.5 km (SPAD Real)"]["scenario"]["channel"]["kind"] == "free_space"
    assert by_name["Enlace Submarino 30 m (Real)"]["scenario"]["channel"]["kind"] == "underwater"
```

- [ ] **Step 3: Run the backend test to verify it fails if Ideal is missing**

Run:

```powershell
..\.venv\Scripts\python.exe -m pytest tests\panel_api\test_phase2.py::test_presets_returns_medium_first_scenarios -q
```

Expected: FAIL if `"Canal ideal"` is not in `/api/presets`; PASS if previous local changes already include it.

- [ ] **Step 4: Extend `presets_payload` if needed**

If `"Canal ideal"` is missing, add this preset at the start of the `presets` list in `panel/api/runtime.py`:

```py
(
    "Canal ideal",
    Scenario(
        pulses=1024,
        clock_rate_hz=1_000_000.0,
        seed=1,
        source=SourceConfig(kind="ideal_single_photon"),
        channel=ChannelConfig(
            kind="ideal",
            distance_km=0.0,
            attenuation_db_km=0.0,
            fixed_loss_db=0.0,
            background_count_rate_hz=0.0,
        ),
        detector=DetectorConfig(
            kind="ideal",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
        timing=TimingConfig(jitter_std_s=0.0),
        post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
    ),
),
```

- [ ] **Step 5: Run backend preset test**

Run:

```powershell
..\.venv\Scripts\python.exe -m pytest tests\panel_api\test_phase2.py::test_presets_returns_medium_first_scenarios -q
```

Expected: PASS.

- [ ] **Step 6: Commit exact backend files only**

```powershell
git add panel/api/runtime.py tests/panel_api/test_phase2.py
git commit -m "add medium-first preset coverage"
```

---

### Task 10: Visual Polish, Lint, Build, And Browser Verification

**Files:**
- Modify: `panel/web/src/index.css`
- Modify: `panel/web/src/App.tsx`
- Modify: component files created above if browser verification reveals overlap.

- [ ] **Step 1: Run frontend lint**

Run from `panel/web`:

```powershell
npm.cmd run lint
```

Expected: PASS.

- [ ] **Step 2: Run frontend build**

Run from `panel/web`:

```powershell
npm.cmd run build
```

Expected: PASS. The Plotly chunk-size warning is acceptable.

- [ ] **Step 3: Run backend tests**

Run from repo root:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run ruff**

Run from repo root:

```powershell
..\.venv\Scripts\python.exe -m ruff check .
```

Expected: PASS.

- [ ] **Step 5: Start the API demo server**

Run from repo root:

```powershell
..\.venv\Scripts\python.exe -m uvicorn panel.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Expected: server starts and serves the API. Keep it running for browser verification.

- [ ] **Step 6: Browser verification**

Open `http://127.0.0.1:8000/` with the Browser tool after building the frontend. Verify:

- First viewport shows `Laboratorio` and the medium gallery.
- Cards for `Canal ideal`, `Fibra telecom`, `Vacio`, `Aire urbano`, `Satelite LEO`, `Submarino`, and `Custom experto` are visible.
- Opening Fiber shows cockpit and inspector.
- Fiber inspector hides `pointing_jitter_rad` and `underwater_extinction_m_inv`.
- Opening Ideal hides fiber, air, satellite, and underwater medium impairment controls.
- Opening Custom shows all catalog fields through search or expert mode.
- A curve can be selected from a recipe without typing raw target names.
- A temporal degradation can be applied without editing JSON.
- Desktop and mobile widths have no horizontal overflow.
- Browser console has no errors.

- [ ] **Step 7: Commit polish fixes**

If this task changes files, commit exact files:

```powershell
git add panel/web/src/index.css panel/web/src/App.tsx panel/web/src/features/lab/MediumGallery.tsx panel/web/src/features/lab/LinkCockpit.tsx panel/web/src/features/designer/FocusedInspector.tsx panel/web/src/features/curves/CurveRecipeBar.tsx panel/web/src/features/dynamics/TemporalPatternBuilder.tsx
git commit -m "polish medium-first dashboard experience"
```

If no files changed in this task, do not create an empty commit.

---

## Final Verification Gate

- [ ] Run from repo root:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

Expected: PASS.

- [ ] Run from repo root:

```powershell
..\.venv\Scripts\python.exe -m ruff check .
```

Expected: PASS.

- [ ] Run from `panel/web`:

```powershell
npm.cmd test -- --run
```

Expected: PASS.

- [ ] Run from `panel/web`:

```powershell
npm.cmd run lint
```

Expected: PASS.

- [ ] Run from `panel/web`:

```powershell
npm.cmd run build
```

Expected: PASS.

- [ ] Run browser verification from Task 10.

- [ ] Check staged and unstaged state:

```powershell
git status -sb
```

Expected: only intentional files are dirty, or the tree is clean after commits. Pre-existing local changes must not be lost.

---

## Self-Review Notes

- Spec coverage:
  - Medium choice including Ideal, Fiber, Vacuum, Air, Satellite, Underwater, Custom: Tasks 2, 7, 10.
  - Realistic defaults: Tasks 2 and 9.
  - Hide irrelevant controls by medium and Custom shows all: Tasks 3, 7, 10.
  - Easy curves from named recipes: Tasks 4, 7, 8, 10.
  - Simple temporal degradation modes: Tasks 5, 7, 10.
  - Cockpit with link path and metrics: Task 7.
  - Existing API/jobs/sweeps/library stay functional: Tasks 8, 9, 10.
  - Responsive polished UI: Tasks 7 and 10.
- Type consistency:
  - `MediumId` comes from `features/lab/mediums.ts`.
  - `CurveRequest` and `CurveRecipeId` come from `features/curves/recipes.ts`.
  - Temporal schedules use the backend-supported `constant` and `linear` profile payloads.
  - Scenario path utilities are shared by store, visibility, and temporal UI.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-14-qkd-medium-first-dashboard-implementation.md`.

Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
