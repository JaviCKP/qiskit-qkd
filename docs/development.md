# Development

This repository is in Phase 9. The package has a type/range-validated domain
schema and a minimal BB84 circuit path backed by Qiskit primitives, plus an event-level
physical layer for fiber loss, detector efficiency, dark counts, timing gates,
dead time, afterpulsing, and distance sweeps. It also has pedagogical
classical post-processing diagnostics for BB84. Phase 4 adds Qiskit Aer
state/readout noise integration, source preparation errors, coherent
polarization misalignment, optical background clicks, controlled transpilation,
and Qiskit/Aer provenance without moving photonic no-click physics into
`NoiseModel`. Phase 4.1 adds dynamic parameter schedules, channel
characterization rows, and temporal BB84 sweeps for plot-ready analysis data.
Phase 5 adds explicit BB84 Eve models with traceable event and metric
diagnostics. Phase 6 adds weak-coherent decoy-state source infrastructure and
per-intensity BB84 statistics. Phase 6.1 adds first-order fiber impairments:
PMD, chromatic dispersion, polarization-dependent loss, and Raman crosstalk.
Phase 6.2 adds asymptotic vacuum+weak decoy diagnostic estimates and a
photon-number-splitting Eve model. Phase 7 adds entanglement-based E91 with
Bell-pair circuits, CHSH diagnostics, source-pair imperfections, and flat Bell
analysis rows. Phase 8 adds non-fiber optical channel models for deep-space,
free-space/satellite, and underwater QKD studies. Phase 9 adds optional visual
analytics and derived metric helpers for publication-ready figures without
making Matplotlib a base dependency.

## Phase 0 Scope

Phase 0 includes:

- A minimal `pyproject.toml`.
- A `src/` package layout with `src/qiskit_qkd/`.
- A `tests/` directory with useful import and side-effect checks.
- A prepared `examples/` directory.
- Development commands for installation, tests, linting, and smoke execution.
- A baseline reading map for Qiskit, Qiskit Aer, packaging, pytest, and QKD.

Phase 0 does not include protocol classes, channels, detectors, attacks,
simulation backends, or functional examples. Those belong to later phases.

## Phase 1 Scope

Phase 1 includes:

- `Scenario`, `ProtocolConfig`, `SourceConfig`, `ChannelConfig`,
  `DetectorConfig`, and `PostProcessingConfig`.
- `Event`, `Metrics`, and `SimulationResult`.
- Parameter validation with units in field names such as `distance_km`,
  `clock_rate_hz`, and `gate_width_s`.
- JSON round-tripping for scenarios and results.
- Centralized seed handling through `make_rng`.
- Aggregate-first result storage with an optional event sample.

Phase 1 does not include physical channel behavior, protocol execution, Qiskit
circuits, or CLI commands.

## Phase 2 Scope

Phase 2 includes:

- `CircuitFactory.bb84_prepare_measure()` for one-qubit BB84 circuits.
- `QiskitSamplerBackend` with `StatevectorSampler` by default and bounded
  primitive batches.
- `BB84Protocol` with ideal source, channel, and detector assumptions.
- BB84 sifting, QBER, and a simplified asymptotic key-rate formula.
- JSON-safe Qiskit execution summaries on `SimulationResult`.
- `examples/bb84_ideal.py`.
- Architecture and parameter documentation.

Phase 2 does not include fiber loss, dark counts, advanced detector behavior,
Eve, decoy BB84, E91, dashboards, CLI commands, Aer noise adapters, or advanced
transpilation.

The numeric QBER and key-rate fields introduced here are legacy-compatible
diagnostics. In current results, `SimulationResult.assessment` distinguishes
undefined QBER from an observed zero and labels the rate scope as pedagogical
and asymptotic.

## Phase 3 Scope

Phase 3 includes:

- `IdealChannel` and `FiberChannel`.
- Fiber transmittance using
  `loss_db = attenuation_db_km * distance_km + fixed_loss_db` and
  `eta_channel = 10 ** (-loss_db / 10)`.
- Photon loss as event-level transmission/no-click, not `amplitude_damping`.
- `ThresholdDetector` with efficiency, dark counts, and double-click policies:
  `discard`, `random`, and `error`.
- BB84 integration with source emission probability, channel transmission, and
  detector outcomes.
- Backend execution only for pulses that were emitted and transmitted.
- Dark-count detections even when no pulse is emitted or transmitted.
- `analysis.sweep_bb84_distance()` returning JSON-safe rows.
- `examples/bb84_fiber_sweep.py`.

Phase 3 does not include Eve, decoy BB84, E91, dashboards, CLI commands, Aer
`NoiseModel` adapters, advanced transpilation, or a `VectorizedBackend`.
`VectorizedBackend` remains postponed because the current bounded Qiskit path is
sufficient for the Phase 3 test suite and small examples.

## Phase 3.5 Scope

Phase 3.5 is the physical-event refinement after Phase 3. Its purpose is to
make the timing model explicit so the simulator does not rely on the
pedagogical simplification that Alice's pulse index and Bob's detection gate
are perfectly aligned.

Phase 3.5 includes:

- Explicit `Event.time_slot` terminology. `Event.index` remains as a compatible
  alias for the shared slot and is not a received-photon counter.
- Bob detection gates derived from `clock_rate_hz`, `gate_width_s`,
  `propagation_delay_s`, `clock_offset_s`, and `clock_drift_ppm`.
- Arrival-time metadata for transmitted photons, including per-pulse jitter.
- Signal assignment to Bob gates with `slot_assignment_policy="discard"` by
  default and `"nearest"` available as an explicit policy.
- Detector dead time and afterpulsing state, because both depend on previous
  detections and cannot be represented by independent per-pulse Bernoulli
  samples alone.
- Public sifting over detected slots and Bob bases. Hidden fields such as
  `transmitted` and the actual arrival time remain simulator diagnostics.

Phase 3.5 remains in the event layer. Timing jitter, dead time,
afterpulsing, clock drift, and gate assignment are not Qiskit gates and should
not be encoded as `NoiseModel` errors. Qiskit should still receive only the
signal rounds that are physically available for quantum measurement.

Phase 3.5 should not include Eve, decoy BB84, E91, dashboards, CLI commands, Aer
`NoiseModel` adapters, or advanced transpilation. It is a physical timing and
detector-state phase, not a protocol-expansion phase.

## Phase 3.6 Scope

Phase 3.6 is a classical post-processing phase. Its purpose is to turn the
current pedagogical key-rate estimate into a more explicit BB84
post-processing pipeline while still avoiding claims of industrial or
composable security.

Phase 3 still computes QBER and a simplified pedagogical asymptotic key rate
from aggregate counters. Phase 3.6 additionally makes the intermediate classical steps
visible through `SimulationResult.classical`:

- Build aligned Alice and Bob sifted-key strings from detected same-basis slots.
- Select a reproducible public sample of sifted bits for QBER estimation.
- Remove the revealed sample from the candidate key.
- Abort before reconciliation when the estimated QBER exceeds the configured
  threshold.
- Add a pedagogical reconciliation method, such as block parity plus binary
  search for likely single-error blocks.
- Track `leak_ec`, the number of public parity or syndrome bits revealed during
  reconciliation.
- Report corrected-key length and residual mismatches for validation runs where
  the simulator can compare Alice and Bob internally.
- Add simple privacy amplification by hashing the corrected key diagnostics
  down to a target length derived from QBER and `leak_ec`.
- Store only key material needed for tests or small examples; large simulations
  should keep aggregate lengths and diagnostics instead of dumping full secrets.

When the configured sample fraction is zero, the implementation reveals no
sample but uses the full sifted strings as a simulator-only diagnostic. It is
labelled `qber_method="full_sifted_key_diagnostic"`, not as protocol knowledge.
The aggregate `metrics.abort`, classical threshold outcome, verification,
key-status, and rate-estimate status remain separate decisions.

Phase 3.6 is explicit about limits. Pedagogical block-parity reconciliation is
useful for teaching and tests, but it is not Cascade, LDPC, finite-key
analysis, or a composable security proof. If QBER is near 50%, Alice and Bob's
sifted strings are effectively uncorrelated and the correct behavior is abort,
not attempted correction.

Phase 3.6 does not include Eve, decoy BB84, E91, dashboards, CLI commands, Aer
`NoiseModel` adapters, or advanced transpilation. It is a classical
post-processing phase layered after sifting and before later protocol
expansions.

## Phase 4 Scope

Phase 4 is the Qiskit/Aer integration phase. Its purpose is to make the
detectable quantum-state part of the channel configurable through Qiskit Aer
while preserving the event-layer model for QKD photonics.

Phase 4 includes:

- `AerNoiseModelAdapter.from_scenario()` for Aer `NoiseModel` construction.
- Channel depolarization through `depolarizing_error` on the circuit channel
  marker.
- Channel dephasing through `phase_damping_error` on the circuit channel
  marker.
- Detector readout error through Aer `ReadoutError`.
- Source preparation error as a sampled logical BB84 bit flip before basis
  encoding.
- Coherent polarization misalignment as explicit Qiskit `ry`/`rz` gates.
- Optical background as event-layer random detector clicks distinct from dark
  counts.
- An explicit BB84 `id` channel marker between Alice preparation and Bob basis
  change.
- `TranspilationOptions` for controlled Qiskit transpilation and
  `seed_transpiler` provenance.
- `QiskitSamplerBackend` support for Aer `SamplerV2` when a noise model is
  supplied.
- Qiskit/Aer version, seed, primitive, counts, noise-model, and transpilation
  summaries in `SimulationResult.qiskit`.
- `examples/bb84_aer_noisy.py` and `examples/bb84_physical_noise.py`.

Phase 4 does not include Eve, decoy BB84, E91, dashboards, CLI commands, or
temporal channel characterization. It also does not encode fiber loss,
no-clicks, detector efficiency, dark counts, dead time, afterpulsing, or timing
gates inside Aer. Those remain event-layer behavior.

## Phase 4.1 Scope

Phase 4.1 is the dynamic communication-conditions phase. Its purpose is to
sample changing link parameters in a way that is academically explicit, easy to
serialize, and ready for later plotting without adding plotting dependencies
yet.

Phase 4.1 includes:

- `DynamicConfig` on `Scenario` for optional time-dependent schedules.
- `ParameterSchedule` with validated `section.field` targets such as
  `source.preparation_error_probability`,
  `channel.background_count_rate_hz`, `detector.efficiency`, and
  `timing.clock_offset_s`.
- `ConstantProfile`, `LinearRampProfile`, and `ExponentialRampProfile` for
  finite time windows.
- `ParameterResolver.scenario_at()` for creating effective immutable scenarios
  at a selected `time_s` without mutating the base scenario.
- `ChannelState`, `channel_state_from_scenario()`, and
  `ChannelCharacterizer` for JSON-safe link-state rows.
- `analysis.sweep_bb84_time()` for running BB84 over selected time points and
  returning flat rows with metrics plus effective scheduled-parameter columns.
- `examples/bb84_dynamic_channel.py`.
- `docs/dynamic_parameters.md`.

Phase 4.1 does not include matplotlib helpers, dashboards, notebooks, CLI
commands, per-pulse nonstationary parameter changes inside one protocol run,
or finite-key security claims for time-varying links. Those rows are designed
so plotting can be added cleanly later.

## Phase 5 Scope

Phase 5 is the BB84 eavesdropping phase. Its purpose is to introduce a clear
adversarial layer without mixing Eve with accidental physical noise or
classical post-processing.

Phase 5 includes:

- `EveConfig` on `Scenario`.
- `qiskit_qkd.eavesdroppers` with `NoEve`, `InterceptResendEve`, and
  `eve_from_config()`.
- Intercept-resend sampling only on surviving signal rounds.
- Eve's basis choice, measured bit, resent state, and disturbance marker stored
  on event fields and JSON-safe tags.
- `Metrics.eve_intercepted_fraction` and
  `Metrics.eve_information_estimate` populated from the run.
- `examples/bb84_eve_intercept_resend.py`.
- `docs/eavesdropping.md`.

Phase 5 does not include decoy-state analysis, coherent attacks,
authentication failure, E91, dashboards, CLI commands, or finite-key/composable
security proofs. Photon-number-splitting attacks are added later in Phase 6.2.

## Phase 6 Scope

Phase 6 is the decoy-state BB84 source-statistics phase. Its purpose is to move
from ideal single-photon emissions toward weak coherent pulses while keeping
the output easy to inspect and plot.

Phase 6 includes:

- `DecoyIntensity` with `name`, `mean_photon_number`, and
  `selection_probability`.
- `SourceConfig(kind="weak_coherent", decoy_intensities=...)`.
- `WeakCoherentDecoySource` with Poisson photon-number sampling.
- Vacuum, single-photon, and multi-photon event tracing through
  `Event.photon_number`, `Event.surviving_photon_number`, and
  `Event.intensity_class`.
- Multi-photon channel survival sampled as `Binomial(n, eta_channel)`.
- Detector signal-click probability
  `1 - (1 - eta_detector)**surviving_photon_number`.
- `SimulationResult.decoy` with JSON-safe per-intensity rows.
- `examples/bb84_decoy.py`.
- `docs/decoy_states.md`.

Phase 6 does not include decoy lower/upper bound estimators, finite-key
analysis, photon-number-splitting attacks, photon-number-resolving detectors,
E91, dashboards, CLI commands, or composable security proofs. The asymptotic
decoy estimator and PNS model are added later in Phase 6.2.

## Phase 6.1 Scope

Phase 6.1 is the advanced fiber-impairment phase. Its purpose is to add useful
link effects without turning the project into a full optical propagation
solver.

Phase 6.1 includes:

- `channels.impairments` with formulas for PMD broadening, chromatic
  broadening, effective timing jitter, state-dependent PDL transmittance,
  Raman count rate, and effective optical background rate.
- `ChannelConfig` fields for PMD/CD/PDL/Raman parameters with validation and
  JSON round-tripping.
- PDL applied before photon-survival sampling using Alice's prepared BB84 bit
  and basis.
- PMD and chromatic dispersion applied as additional timing jitter, causing
  observable `early`/`late` timing discards.
- Raman crosstalk added to the detector background rate, producing background
  clicks without running signal circuits.
- Dynamic scheduling support for scalar impairment parameters.
- `ChannelCharacterizer` columns for raw and derived impairment values.
- `tests/test_fiber_impairments.py`.

Phase 6.1 does not include stochastic Jones-matrix propagation, full spectral
pulse-shape evolution, wavelength-resolved Raman models, dual-detector
receiver imbalance, plotting helpers, dashboards, CLI commands, finite-key
analysis, or composable security proofs.

## Phase 6.2 Scope

Phase 6.2 is the decoy-diagnostic and PNS phase. Its purpose is to move from
observable decoy statistics to a useful asymptotic rate diagnostic while
keeping finite-key claims out of scope.

Phase 6.2 includes:

- `postprocessing.decoy.estimate_vacuum_weak_decoy_security()` for the standard
  signal + weak decoy + vacuum asymptotic BB84 estimator.
- Lower bound on single-photon yield `Y1`, lower bound on single-photon gain
  `Q1`, and upper bound on single-photon error rate `e1`.
- A decoy secret-key-rate diagnostic using the observed basis-sift factor and
  the configured error-correction efficiency.
- `SimulationResult.decoy["security"]` with flat JSON-safe estimator fields;
  `security` is a retained legacy key, not a formal-proof claim.
- `PostProcessingConfig.decoy_security_estimation_enabled` and
  `decoy_security_method` (legacy names) for switching asymptotic decoy
  diagnostics on or off.
- `analysis.decoy_rows_from_result()` for flat plot-ready intensity rows and
  the legacy-named `security` diagnostic row.
- `PhotonNumberSplittingEve`, configured through
  `EveConfig(kind="photon_number_splitting")` or `kind="pns"`.
- PNS splitting of multi-photon pulses without introducing BB84 basis errors.
- Optional blocking of single-photon pulses to model a lossy-link PNS strategy.
- Event tags for PNS actions, forwarded photons, blocked signals, and Eve's
  known sifted bits.

Phase 6.2 does not include finite-key confidence intervals, composable
security, coherent/collective attacks, detector-control attacks, or
photon-number-resolving detectors.

## Phase 7 Scope

Phase 7 is the E91 entanglement-based protocol phase. Its purpose is to show
that the package can support protocols beyond prepare-and-measure BB84 while
preserving the same Qiskit/event/post-processing boundaries.

Phase 7 includes:

- `E91Config` on `Scenario` with Bell state, Alice/Bob angular settings, key
  setting pairs, CHSH terms, Bob key-bit correction, and CHSH enable switch.
- `SourceConfig(kind="entangled_pair")` and `EntangledPairSource` for
  Bernoulli Bell-pair emission.
- `CircuitFactory.e91_bell_measure()` for inspectable two-qubit Bell-pair
  circuits.
- `QiskitSamplerBackend.measure_e91_batch()` returning reproducible Alice/Bob
  measurement pairs.
- `E91Protocol` with Bob-arm channel survival, timing gates, independent Alice
  and Bob threshold detectors, coincidence filtering, key QBER, and observed
  CHSH `S` with assessment sample sizes.
- Source-pair preparation imperfection using random Pauli errors on Bob's
  qubit, controlled by `SourceConfig.preparation_error_probability`.
- Reuse of channel coherent rotations, Aer depolarizing/phase-damping/readout
  noise, detector noise, optical background, dead time, and afterpulsing.
- `SimulationResult.bell` and `analysis.bell_rows_from_result()` for
  plot-ready setting rows.
- `examples/e91_chsh.py` and `docs/e91.md`.

Phase 7 deliberately does not include loophole-free Bell-test analysis,
device-independent finite-key proofs, dual-arm asymmetric channel configs,
SPDC multi-pair statistics, entanglement swapping, repeaters, or E91-specific
side-channel attacks.

The CHSH conclusion is a detected-coincidence, fair-sampling diagnostic. There
is no significance test or confidence interval, and neither detection nor
locality loopholes are closed.

## Phase 8 Scope

Phase 8 is the non-fiber optical-channel phase. Its purpose is to broaden the
physical link layer while keeping the simulator modular and easy to
characterize.

Phase 8 includes:

- `SpaceChannel` for vacuum/deep-space geometric loss.
- `FreeSpaceChannel` for atmospheric/satellite extinction, scintillation, and
  pointing jitter.
- `UnderwaterChannel` for Beer-Lambert water extinction, optional fading, and
  scattering-induced temporal broadening.
- `ChannelConfig` fields for wavelength, apertures, divergence, atmospheric
  extinction, scintillation, pointing jitter, underwater extinction, and
  underwater scattering broadening.
- `sample_transmittance(rng)` as an optional pulse-level channel interface used
  before binomial photon survival sampling.
- Dynamic scheduling support for the new scalar channel parameters.
- `ChannelCharacterizer` columns for baseline geometry, extinction, fading
  configuration, and scattering broadening.
- `docs/optical_channels.md` and `tests/test_space_channels.py`.

Phase 8 does not include orbital mechanics, weather time series, adaptive
optics, full wave-optics propagation, wavelength-resolved underwater
scattering, or automatic conversion from medium conditions to Aer quantum
noise. Those can be added as later characterization layers.

## Phase 9 Scope

Phase 9 is the visual analytics phase. Its purpose is to turn the existing
plot-ready rows into attractive, reproducible figures while keeping plotting
optional and outside the simulation core.

Phase 9 includes:

- Optional `plot` extra with `matplotlib>=3.8`.
- `analysis.metric_rows_from_results()` for flattening `SimulationResult`
  objects into comparison rows.
- `analysis.add_derived_metrics()` for ratios such as detected fraction,
  sifted fraction, timing-discard fraction, QBER margin, CHSH margin, and
  privacy efficiency.
- `analysis.summarize_metric_rows()` for repeated-seed aggregation with mean,
  standard deviation, min, max, p05, p95, per-metric finite counts, and
  separate legacy-abort versus authoritative threshold-decision fractions.
- `analysis.secure_distance_limit()` (legacy name) as a sampled-grid,
  assessment-gated pedagogical-rate distance diagnostic, not a certified
  range. A positive legacy rate and `abort=False` alone are insufficient.
- `qiskit_qkd.visualization` generic plotters for metric sweeps, threshold
  curves, heatmaps, and stacked count budgets.
- Domain recipes for BB84 distance summaries, channel comparison, decoy
  intensity summaries, E91 CHSH heatmaps, Eve trade-offs, and timing counts.
- `examples/bb84_visualization.py` and `docs/visualization.md`.

Phase 9 does not include dashboards, interactive GUI state, notebook-only
dependencies, CLI commands, automatic report generation, finite-key confidence
intervals, or new security claims. Those can build on the same row and figure
APIs later.

## Environment

Use Python 3.12 or newer, matching the package metadata. Python 3.12 is a good
default for local development.

Create and activate a virtual environment if the project is not already running
inside one:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Install the package in editable mode:

```powershell
python -m pip install -e .
```

Install development dependencies when working on tests or linting:

```powershell
python -m pip install -e ".[dev]"
```

Install the optional Aer dependency when working on noise models or Aer
primitive integrations:

```powershell
python -m pip install -e ".[dev,aer]"
```

## Commands

Run the test suite:

```powershell
python -m pytest
```

Run lint checks:

```powershell
python -m ruff check .
```

Run the ideal BB84 demo:

```powershell
python examples/bb84_ideal.py
```

Run the fiber sweep demo:

```powershell
python examples/bb84_fiber_sweep.py
```

Run the Aer noisy BB84 demo:

```powershell
python examples/bb84_aer_noisy.py
```

Run the layered physical-noise BB84 demo:

```powershell
python examples/bb84_physical_noise.py
```

Run the dynamic communication-conditions demo:

```powershell
python examples/bb84_dynamic_channel.py
```

Run the Eve intercept-resend demo:

```powershell
python examples/bb84_eve_intercept_resend.py
```

Run the decoy-state BB84 demo:

```powershell
python examples/bb84_decoy.py
```

Run a minimal import smoke check:

```powershell
python -c "import qiskit_qkd; print(qiskit_qkd.__version__)"
```

There is no CLI command in Phase 6. CLI entry points should be added only when a
real user-facing command exists.

## Reading Baseline

Study these topics before implementing the next phases:

| Area | Topics | Why it matters |
| --- | --- | --- |
| Qiskit circuits | `QuantumCircuit`, measurements, `ClassicalRegister`, bit ordering, circuit drawing | BB84 and E91 must expose inspectable circuits instead of hiding the quantum path inside numeric code. |
| Qiskit primitives | `StatevectorSampler`, `StatevectorEstimator`, `SamplerV2`, `EstimatorV2`, primitive unified blocs | Later backends should follow the current primitive model rather than older sampler APIs. |
| Qiskit Aer | `NoiseModel`, `ReadoutError`, `depolarizing_error`, `phase_damping_error`, Aer primitive usage | State noise and readout noise belong in Aer adapters; photon loss and no-click events need a QKD event layer. |
| Packaging | `pyproject.toml`, `src/` layout, optional dependencies, future script entry points | The project must install cleanly with `pip install -e .` and keep heavy tools optional where possible. |
| pytest | Test discovery, fixtures, parametrization, deterministic seeds, `tmp_path` | Simulation tests must be reproducible and fast enough to run on every phase. |
| QKD foundations | BB84, E91, NIST QKD background, authenticated classical channel assumptions | The implementation must make protocol limits clear and avoid claiming complete security proofs. |

Primary references:

- [IBM Quantum Documentation: Qiskit circuit model and `QuantumCircuit`](https://quantum.cloud.ibm.com/docs/en/api/qiskit/circuit).
- [IBM Quantum Documentation: Qiskit primitives and V2 primitive interfaces](https://quantum.cloud.ibm.com/docs/en/guides/primitives).
- [Qiskit Aer API: `NoiseModel`](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.noise.NoiseModel.html), [`ReadoutError`](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.noise.ReadoutError.html), [`depolarizing_error`](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.noise.depolarizing_error.html), and [`phase_damping_error`](https://qiskit.github.io/qiskit-aer/stubs/qiskit_aer.noise.phase_damping_error.html).
- [Python Packaging User Guide: writing `pyproject.toml`](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
- [pytest good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html) and [parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html).
- Bennett and Brassard 1984: BB84 protocol.
- [Ekert 1991: E91 protocol](https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.67.661).
- [NIST background on quantum key distribution](https://www.nist.gov/news-events/news/2004/04/background-quantum-key-distribution).

## Code Conventions

- Keep package import side effects out of `qiskit_qkd.__init__`.
- Import Qiskit and Aer only inside modules that need them.
- Keep comments short and tied to non-obvious design decisions.
- Prefer deterministic tests with explicit seeds once simulations exist.
- Add directories only when a phase introduces real code for that area.
