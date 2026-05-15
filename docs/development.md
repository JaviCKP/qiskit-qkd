# Development

This repository is in Phase 3.5. The package has a validated domain model, a
minimal BB84 circuit path backed by Qiskit primitives, and an event-level
physical layer for fiber loss, detector efficiency, dark counts, timing gates,
dead time, afterpulsing, and distance sweeps.

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

Phase 3.6 is a future classical post-processing phase. It is not implemented
yet. Its purpose is to turn the current pedagogical key-rate estimate into a
more explicit BB84 post-processing pipeline while still avoiding claims of
industrial or composable security.

Phase 3 currently computes QBER and a simplified secret-key rate directly from
aggregate counters. Phase 3.6 should make the intermediate classical steps
visible:

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
- Add simple privacy amplification, for example hashing the corrected key down
  to a target length derived from QBER and `leak_ec`.
- Store only key material needed for tests or small examples; large simulations
  should keep aggregate lengths and diagnostics instead of dumping full secrets.

Phase 3.6 should be explicit about limits. Pedagogical block-parity
reconciliation is useful for teaching and tests, but it is not Cascade, LDPC,
finite-key analysis, or a composable security proof. If QBER is near 50%, Alice
and Bob's sifted strings are effectively uncorrelated and the correct behavior
is abort, not attempted correction.

Phase 3.6 should not include Eve, decoy BB84, E91, dashboards, CLI commands, Aer
`NoiseModel` adapters, or advanced transpilation. It is a classical
post-processing phase layered after sifting and before later protocol
expansions.

## Environment

Use Python 3.11 or newer. Python 3.12 is a good default for local development.

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

Run a minimal import smoke check:

```powershell
python -c "import qiskit_qkd; print(qiskit_qkd.__version__)"
```

There is no CLI command in Phase 3. CLI entry points should be added only when a
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
