# Development

This repository is in Phase 2. The package has a validated domain model and a
minimal ideal BB84 circuit path backed by Qiskit primitives.

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

Run a minimal import smoke check:

```powershell
python -c "import qiskit_qkd; print(qiskit_qkd.__version__)"
```

There is no CLI command in Phase 2. CLI entry points should be added only when a
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
