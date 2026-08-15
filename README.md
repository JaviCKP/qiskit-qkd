# qiskit-qkd

`qiskit-qkd` is a Qiskit-first Python package for quantum key distribution
simulations. It currently includes a type/range-validated configuration/domain
schema and an ideal BB84 path backed by real Qiskit circuits and Sampler
primitives, plus the Phase 3
event layer for fiber loss, detector efficiency, dark counts, and distance
sweeps. Phase 3.5 adds explicit timing metadata, Bob detection gates, clock
offset/drift, jitter, dead time, and afterpulsing in the event layer.
Phase 3.6 adds a pedagogical classical post-processing layer with reproducible
QBER sampling, block-parity reconciliation diagnostics, error-correction
leakage accounting, and optional privacy-amplification digests. Phase 4 adds
Qiskit Aer `NoiseModel` integration for detectable quantum-state and readout
noise, coherent polarization misalignment, source preparation errors, optical
background clicks, plus controlled transpilation and Qiskit/Aer provenance.
Phase 4.1 adds dynamic parameter schedules and channel characterization rows,
so time-varying communication conditions can be sampled cleanly before adding
plotting or dashboards. Phase 5 adds explicit BB84 eavesdropper models with
`NoEve` and a pedagogical `InterceptResendEve` attack. Phase 6 adds
weak-coherent decoy intensities and per-intensity BB84 statistics. Phase 6.1
adds first-order fiber impairments for PMD, chromatic dispersion,
polarization-dependent loss, and Raman crosstalk. Phase 6.2 adds asymptotic
vacuum+weak decoy diagnostic estimates and a traceable photon-number-splitting
Eve model. Phase 7 adds E91 entanglement-based QKD with Bell-pair circuits,
CHSH diagnostics, source-pair imperfections, and plot-ready Bell rows. Phase 8
adds non-fiber optical channels for deep-space, free-space/satellite, and
underwater QKD link studies. Phase 9 adds optional Matplotlib visual analytics
for sweep rows, decoy diagnostics, E91 correlations, Eve trade-offs, timing
summaries, and publication-ready SVG/PNG exports.

## Scientific Interpretation

This is an educational Monte Carlo simulator, not a security certification
tool. Result interpretation is explicit in `SimulationResult.assessment`:
`qber_defined` distinguishes a measured zero QBER from the legacy numeric
placeholder `metrics.qber == 0.0` used when there are no sifted bits;
`data_status`, `key_status`, and `rate_estimate_status` distinguish missing
data, a post-processing outcome, and an asymptotic rate estimate. The legacy
`metrics.abort` flag records only its historical aggregate-threshold decision.
It is not equivalent to the classical sample-threshold decision, successful
verification, an available key estimate, or formal security.

All reported key rates, including the field named `secret_key_rate_bps`, are
pedagogical asymptotic diagnostics. They are not finite-key bounds, composable
security proofs, production key material, or guarantees for a real link. With
`qber_sample_fraction=0`, the classical pipeline uses the full sifted key only
as a simulator diagnostic; that value is not a publicly obtainable estimate
and is labelled `qber_method="full_sifted_key_diagnostic"`.

E91 reports an observed CHSH statistic from detected coincidences. A value
above 2 is an observed threshold crossing in the simulated, post-selected
sample under a fair-sampling interpretation. No significance test, confidence
interval, detection/locality loophole closure, or device-independent security
claim is performed.

Configurable CHSH terms are restricted to a genuine four-term, two-setting
per party witness with local bound 2. Duplicate/incomplete setting grids and
sign patterns with local bound 4 are rejected instead of being compared with
the wrong threshold.

For reproducibility, retain the requested scenario, its digest and seed, the
effective model snapshot, and the backend/Qiskit/Aer version and seed metadata.
Requested parameters describe user intent; `provenance.effective_model`
describes what the selected source, channel, detector, and protocol actually
used. Repeating a seed is meaningful only with the same effective model,
software versions, backend path, and primitive configuration.

Sweep rows keep `requested_scenario_digest` and
`effective_scenario_digest` separately so a base request is not confused with
the concrete point that was executed.

The current `SimulationResult` envelope is schema v2 and requires a non-null,
evidence-checked `assessment`. The reader accepts schema-v1 archives and marks
the derived assessment/provenance in `provenance.archive_load`; explicit
`to_legacy_dict()`/`to_legacy_json()` exports omit the v2 assessment for old
readers. Loading an archive never substitutes the current runtime version or a
newly inferred effective model as historical producer evidence.

The current payload does not hash the implementation checkout and does not
record the Python runtime version; archive the VCS revision and environment
lock separately when exact long-term reproduction matters.

## Installation

```powershell
python -m pip install -e .
```

Install the development tools when working on the repository:

```powershell
python -m pip install -e ".[dev]"
```

Install the optional Aer dependency when working on noisy simulation paths:

```powershell
python -m pip install -e ".[dev,aer]"
```

Install the optional plotting dependency when generating figures:

```powershell
python -m pip install -e ".[dev,plot]"
```

## Development Checks

```powershell
python -m pytest
python -m ruff check .
```

## Visual QKD Panel

The local dashboard lives in `panel/` and provides the React/FastAPI workflow
for designing scenarios, characterizing the link, running jobs, saving
experiments, and generating curve studies.

```powershell
cd panel\web
npm.cmd install
npm.cmd run build
cd ..\..
python -m panel.api
```

The demo serves the built web app and API at `http://127.0.0.1:8000`.

## Ideal BB84 Demo

```powershell
python examples/bb84_ideal.py
```

## Fiber BB84 Sweep

```powershell
python examples/bb84_fiber_sweep.py
```

This example sweeps BB84 over a simple fiber model and prints distance, optical
loss, detections, gain, sifted bits, QBER, and the legacy pedagogical
asymptotic key-rate estimate.

## BB84 Visualization Demo

```powershell
python examples/bb84_visualization.py
```

With `qiskit-qkd[plot]` installed, this example saves
`examples/figures/bb84_distance_summary.svg`. Without the optional extra it
prints the installation hint and exits cleanly.

## Aer Noisy BB84 Demo

```powershell
python examples/bb84_aer_noisy.py
```

This example compares ideal BB84 with Aer depolarizing, phase-damping, and
readout-noise scenarios. Fiber loss and detector no-click behavior remain in
the event layer, not in the Aer `NoiseModel`.

## Layered Physical Noise Demo

```powershell
python examples/bb84_physical_noise.py
```

This example compares ideal BB84 with source preparation errors, coherent
polarization misalignment, and optical background clicks.

## Dynamic Channel Demo

```powershell
python examples/bb84_dynamic_channel.py
```

This example attaches time profiles to a `Scenario`, samples effective
communication parameters at selected seconds, and prints plot-ready rows for
BB84 comparison.

## Eve Intercept-Resend Demo

```powershell
python examples/bb84_eve_intercept_resend.py
```

This example compares BB84 without Eve against partial and full
intercept-resend attacks, reporting QBER plus Eve trace metrics.

## Decoy-State BB84 Demo

```powershell
python examples/bb84_decoy.py
```

This example samples weak-coherent `signal`, `decoy`, and `vacuum` intensities
and prints per-intensity gain, QBER, multi-photon counts, and the asymptotic
vacuum+weak decoy estimate for `Y1`, `e1`, `Q1`, and a pedagogical asymptotic
key-rate diagnostic. The same
data can be flattened for plotting with `decoy_rows_from_result(result)`.

## E91 CHSH Demo

```powershell
python examples/e91_chsh.py
```

This example runs an entanglement-based E91 singlet simulation, prints
coincidences, key QBER, CHSH `S`, and per-setting correlations, then compares
against a noisy Bell-pair source.

## Fiber Impairments

The fiber event layer can also model PMD/CD timing broadening, PDL
state-dependent loss, and Raman background from classical channels. These
parameters are exposed through `ChannelConfig` and `ChannelCharacterizer` for
plot-ready sweeps.

## Optical Channel Families

`ChannelConfig.kind` supports `ideal`, `fiber`, `space`, `free_space`, and
`underwater`. The non-fiber models add diffraction-limited geometric loss,
atmospheric extinction, scintillation fading, pointing jitter, Beer-Lambert
water extinction, and underwater scattering broadening while keeping quantum
state noise explicit in Qiskit/Aer.

## Smoke Execution

```powershell
python -c "import qiskit_qkd; print(qiskit_qkd.__version__)"
```

See [docs/development.md](docs/development.md) for the development command
reference. See [docs/domain_model.md](docs/domain_model.md) for the data model,
[docs/architecture.md](docs/architecture.md) for the Qiskit/QKD boundary, and
[docs/parameters.md](docs/parameters.md) for units and formulas. See
[docs/qiskit_integration.md](docs/qiskit_integration.md) for Aer noise and
transpilation details, [docs/dynamic_parameters.md](docs/dynamic_parameters.md)
for Phase 4.1 temporal schedules and channel characterization, and
[docs/eavesdropping.md](docs/eavesdropping.md) for Phase 5 Eve models, and
[docs/decoy_states.md](docs/decoy_states.md) for Phase 6 decoy BB84, and
[docs/e91.md](docs/e91.md) for Phase 7 E91, and
[docs/optical_channels.md](docs/optical_channels.md) for Phase 8 channel
families, and [docs/visualization.md](docs/visualization.md) for Phase 9
visual analytics.

CLI commands, finite-key decoy proofs, loophole-free
device-independent E91 analysis, orbital/weather propagation, automatic report
generation, and full spectral/Jones-matrix propagation models remain future
phases.
