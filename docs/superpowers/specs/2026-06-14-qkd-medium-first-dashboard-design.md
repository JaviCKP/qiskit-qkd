# QKD Medium-First Visual Dashboard Design

## Purpose

The current dashboard exposes the full simulation model, but it feels heavy
because it starts with every technical control. The redesign must make the
first interaction visual and simple while preserving the existing professional
granularity.

The new experience starts from the physical medium. The user chooses a realistic
medium such as ideal channel, fiber, vacuum/deep space, air/free-space,
satellite, underwater, or custom. The UI then shows only the controls that make
physical sense for that medium. Custom keeps the full catalog editable.

## User Goals

- Start from a realistic QKD scenario without needing to understand every
  parameter first.
- See the link behavior visually before editing details.
- Avoid irrelevant controls: fiber should not show satellite pointing controls;
  underwater should not show fiber dispersion controls unless custom mode is
  active.
- Keep access to every granular parameter for research-grade tweaking.
- Use realistic default values backed by the existing domain model and preset
  work.
- Make the UI feel polished, scientific, and pleasant rather than like a raw
  schema form.
- Make curves and temporal dynamics easy to create from named recipes instead
  of asking the user to configure raw sweep axes first.

## Approved Direction

Use a medium-first laboratory:

1. A visual medium gallery is the entry point.
2. Selecting a medium loads a realistic preset and a focused control surface.
3. A cockpit shows the source -> medium -> detector -> post-processing path,
   live metrics, and the primary curve.
4. An advanced inspector preserves all granular controls, filtered by medium.
5. Curves and temporal behavior use guided recipes with advanced expansion.
6. Custom mode exposes every parameter and behaves like the current full editor,
   but with better layout, search, grouping, and visual feedback.

## Medium Model

Add a UI-level medium family concept. It maps to existing `Scenario` and
`ChannelConfig.kind` values, but it is presented in domain language.

| Medium | Channel kind | Default posture | Visible controls |
| --- | --- | --- | --- |
| Ideal | `ideal` | Clean pedagogical baseline with no channel loss or medium-specific impairments | pulses, protocol/source, detector ideal/threshold choice, seed, post-processing, optional noise/security toggles |
| Fiber | `fiber` | Telecom fiber with realistic attenuation, PMD, CD, Raman, PDL, SNSPD defaults | fiber loss, distance, wavelength, dispersion, PMD, PDL, Raman, detector timing |
| Vacuum | `space` or `deep_space` | Diffraction-limited low-background deep-space or lab vacuum path | distance, aperture, wavelength, beam divergence/geometric loss, detector efficiency |
| Air | `free_space` | Urban or terrestrial free-space link | atmospheric extinction, scintillation, pointing jitter, background counts, apertures |
| Satellite | `free_space` or `space` with satellite preset metadata | LEO-style optical link | altitude/range proxy, pointing jitter, apertures, atmospheric loss, scintillation, background |
| Underwater | `underwater` | Blue-green underwater link | water extinction, scattering broadening, short range, apertures, background |
| Custom | any supported kind | Full expert mode | every catalog field, including cross-medium parameters |

The medium family must be stored in UI state or experiment metadata, not forced
into the core schema unless the backend later needs it. Existing scenarios must
still load correctly. If a loaded experiment has no medium metadata, infer it
from `channel.kind`.

## Realistic Defaults

Presets must be realistic enough for a final-year project demonstration:

- Ideal: zero channel loss, no medium background, deterministic baseline seed,
  and a small pulse count suitable for quick demonstrations.
- Fiber: 1550 nm, 0.2 dB/km SMF attenuation, SNSPD efficiency around 0.85,
  low dark counts, decoy weak coherent source.
- Air/free-space: 850 nm or 1550 nm depending on preset, realistic urban
  extinction, scintillation, pointing jitter, Si-SPAD or SNSPD detector.
- Satellite/vacuum: physically plausible apertures, wavelength, geometric loss,
  and low background for space/vacuum cases.
- Underwater: blue-green wavelength around 520 nm, extinction in inverse meters,
  short practical distances, scattering broadening, moderate background.
- Custom: starts from the closest selected preset or a neutral default, then
  allows full editing.

Preset cards should explain their assumptions in concise labels, not long
documentation text. Detailed provenance can appear in tooltips or an advanced
details panel.

## Interaction Design

### First Screen

The first screen is `Laboratorio`.

It contains:

- Medium gallery with cards for Ideal, Fiber, Vacuum, Air, Satellite,
  Underwater, and Custom.
- Each card shows a simple icon, expected range, detector type, realism badge,
  and a tiny sparkline or metric preview when data is available.
- Primary actions: Open, Compare, Run.
- A compact status strip for API status, validation digest, and active preset.

No raw schema sections should appear on the first screen.

### Cockpit

After selecting a medium, the cockpit becomes the working surface:

- Link diagram: Source -> Medium -> Detector -> Classical post-processing.
- Live metric tiles: loss, transmittance, QBER risk, sifted bits, SKR, dark
  probability, timing spread.
- Main chart: default curve appropriate to the medium.
  - Ideal: QBER/SKR baseline vs pulses or detector efficiency.
  - Fiber: SKR and QBER vs distance.
  - Vacuum or satellite: gain/SKR vs distance or pointing loss.
  - Air: QBER/SKR vs atmospheric extinction or distance.
  - Underwater: gain/QBER vs distance or water extinction.
  - Custom: user-selected curve recipe.
- Quick toggles for protocol/security family: BB84, decoy, Eve, E91 where
  applicable.
- Run and save actions remain visible but restrained.

### Easy Curves

Curves must be recipe-driven. The default flow is:

1. Pick a question in plain language, such as "What happens if distance grows?"
   or "What happens if alignment gets worse?"
2. Pick the metric family: secure key rate, QBER, gain, CHSH, timing, or Eve
   information.
3. Press Run.

The app translates that choice into the existing sweep API. Advanced users can
open the generated recipe to edit axis target, min/max/steps, series target,
repeats, scale, and export settings.

Required one-click recipes:

- SKR/QBER vs distance.
- QBER vs detector dark counts.
- SKR/QBER vs mean photon number.
- QBER vs Eve strength.
- CHSH vs depolarization.
- Gain/QBER vs pointing jitter.
- Gain/QBER vs water extinction.
- Metrics vs time for temporal dynamics.

The curve UI should keep the generated axis visible as a readable sentence,
for example: "Sweep fiber distance from 0 to 120 km in 25 points." Raw target
names such as `channel.distance_km` remain available in advanced mode.

### Temporal Dynamics

Temporal modes must be simplified into named patterns. The user should not need
to manually understand `start_s`, `end_s`, `start_value`, `end_value`, and
profile kind before seeing a result.

Required temporal patterns:

- Stable link: parameter stays constant.
- Gradual degradation: QBER-driving parameter worsens over time.
- Recovery: parameter improves over time.
- Drift: clock offset, alignment, distance, or loss changes linearly.
- Burst/noise event: background, dark counts, or error spikes for a short
  interval.

Each pattern presents plain controls:

- Affected phenomenon: loss, QBER/error, alignment, background, timing, or Eve.
- Severity: mild, moderate, severe, plus exact advanced values.
- Duration: short, medium, long, plus exact advanced values.
- Direction: increasing, decreasing, or spike where applicable.

The UI maps those plain choices to the existing dynamic schedule payload. An
advanced expansion shows the generated target and numeric profile, and custom
mode can edit the raw schedule list directly.

### Focused Inspector

The inspector replaces the raw wall of controls:

- It groups controls into Source, Medium, Detector, Timing, Security, Dynamics,
  and Post-processing.
- It filters fields by active medium.
- It has a search box that can reveal matching hidden controls.
- It has a visible `Expert: show all` toggle. Turning it on temporarily exposes
  the full catalog without changing the medium.
- It uses sliders for bounded numeric values, inputs for exact values, toggles
  for booleans, segmented controls for small enumerations, and tables for decoy
  intensities.
- It keeps validation messages next to the affected control and summarizes them
  at the top.

### Custom Mode

Custom mode is the explicit escape hatch:

- It exposes every catalog field by default.
- It keeps the same cockpit and live metrics.
- It lets the user choose any `channel.kind` and cross-medium parameters.
- It marks physically unusual combinations as warnings, not hard blockers,
  unless backend validation rejects them.

## Architecture

Keep the backend scenario model intact. The redesign should mainly restructure
the web app:

- Split the large `App.tsx` into feature modules.
- Add a UI metadata layer for medium families, preset card copy, icons, default
  curve recipes, and field visibility rules.
- Reuse the existing catalog, validation, characterization, dynamics, sweeps,
  runs, and experiments API clients.
- Do not duplicate backend validation in the UI. The UI may hide irrelevant
  fields, but the backend remains authoritative.

Suggested frontend modules:

- `features/lab/mediums.ts`: medium definitions, default presets, field groups,
  and curve recipes.
- `features/lab/MediumGallery.tsx`: first-screen gallery.
- `features/lab/LinkCockpit.tsx`: diagram, metrics, and main curve shell.
- `features/curves/CurveRecipeBar.tsx`: plain-language curve recipes and
  advanced generated-axis editor.
- `features/dynamics/TemporalPatternBuilder.tsx`: named temporal modes that
  generate dynamic schedules.
- `features/designer/FocusedInspector.tsx`: filtered granular editor.
- `features/designer/fieldVisibility.ts`: medium-specific visibility rules.
- `features/curves/CurveWorkbench.tsx`: existing curve workflow moved out of
  `App.tsx`.
- `features/library/LibraryView.tsx` and `features/execution/ExecutionView.tsx`:
  existing views extracted for clarity.

## Data Flow

1. App loads health, catalog, presets, and current scenario.
2. Medium gallery maps presets and medium definitions into visual cards.
3. Selecting a medium loads the associated scenario into the existing designer
   store and stores the active medium family in UI state.
4. Validation, characterization, dynamics, and curve previews run from the same
   scenario object as today.
5. The inspector derives visible fields from catalog + active medium + expert
   toggle.
6. Saving an experiment includes scenario, tags, curve recipes, and optional UI
   metadata such as active medium family.

## Error Handling

- API offline: keep the gallery visible with disabled run/preview actions and a
  clear status indicator.
- Validation error: show field-level errors and a compact summary.
- Hidden-field validation error: surface the affected group and offer to reveal
  the control.
- Physically unusual but valid custom combination: warning badge, not failure.
- Sweep/run failure: keep the failed job details visible with retry and copy
  diagnostics actions.

## Visual Requirements

- The app should feel like a scientific instrument, not a landing page.
- Use a restrained dark interface with multiple accent colors tied to medium
  families, avoiding a one-note palette.
- Use icons in buttons and medium cards.
- Avoid nested cards inside cards.
- Keep dense controls readable and stable across desktop and mobile.
- The first viewport must show the medium choice or active cockpit immediately.
- Charts must be visible, responsive, and non-overlapping.
- No horizontal overflow on mobile or desktop.

## Testing And Verification

Automated checks:

- Unit test medium filtering: fiber hides satellite/air/underwater-only fields;
  ideal hides physical-medium impairment fields; custom shows all catalog
  fields.
- Unit test medium inference from existing scenarios.
- Unit test that selecting a medium loads its preset scenario.
- Unit test that curve recipes produce the expected sweep axis payload.
- Unit test that temporal patterns produce the expected dynamic schedule
  payload.
- Existing App smoke test updated for `Laboratorio` entry.
- Backend tests continue to cover presets and validation.

Manual/browser checks:

- Open the app and confirm the first screen is the medium gallery.
- Select Ideal and confirm medium-specific physical controls are hidden.
- Select Fiber and confirm only fiber-relevant medium controls appear.
- Select Air/Satellite and confirm pointing/scintillation controls appear while
  fiber dispersion controls are hidden.
- Select Underwater and confirm water extinction/scattering controls appear.
- Select Custom and confirm all controls are reachable.
- Create a curve from a one-click recipe without editing raw axis names.
- Create a gradual temporal degradation and verify the generated chart shows the
  parameter worsening over time.
- Run a default curve and a job from a selected realistic preset.
- Verify mobile and desktop layouts have no horizontal overflow.

## Non-Goals

- Do not change the core QKD simulation model solely for UI organization.
- Do not remove advanced controls.
- Do not add remote persistence or authentication.
- Do not turn the app into a marketing landing page.
- Do not block custom physically unusual scenarios unless backend validation
  already treats them as invalid.

## Acceptance Criteria

- A user can choose between ideal, fiber, vacuum, air, satellite, underwater,
  and custom from the first screen.
- Each non-custom medium shows realistic defaults and only relevant controls by
  default.
- Custom exposes the full granular editor.
- Curves can be created from simple named recipes, while advanced sweep editing
  remains available.
- Temporal error/degradation modes can be created from named patterns, while raw
  schedule editing remains available in advanced/custom mode.
- The cockpit shows the link path, live metrics, and a meaningful chart without
  requiring the user to open raw schema sections.
- Existing scenario validation, jobs, sweeps, library import/export, and
  experiment saving still work.
- The UI is visually polished, responsive, and free of obvious overlap or
  horizontal scrolling.
