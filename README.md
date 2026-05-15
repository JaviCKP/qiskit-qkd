# qiskit-qkd

`qiskit-qkd` is a Qiskit-first Python package for quantum key distribution
simulations. It currently includes the validated domain model, an ideal BB84
path backed by real Qiskit circuits and Sampler primitives, and the Phase 3
event layer for fiber loss, detector efficiency, dark counts, and distance
sweeps. Phase 3.5 adds explicit timing metadata, Bob detection gates, clock
offset/drift, jitter, dead time, and afterpulsing in the event layer.

Phase 3.6 is documented as the next classical post-processing refinement:
pedagogical error reconciliation, error-correction leakage accounting, and
privacy amplification. It remains future work.

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

## Development Checks

```powershell
python -m pytest
python -m ruff check .
```

## Ideal BB84 Demo

```powershell
python examples/bb84_ideal.py
```

## Fiber BB84 Sweep

```powershell
python examples/bb84_fiber_sweep.py
```

This example sweeps BB84 over a simple fiber model and prints distance, optical
loss, detections, gain, sifted bits, QBER, and secret-key rate.

## Smoke Execution

```powershell
python -c "import qiskit_qkd; print(qiskit_qkd.__version__)"
```

See [docs/development.md](docs/development.md) for the development command
reference. See [docs/domain_model.md](docs/domain_model.md) for the data model,
[docs/architecture.md](docs/architecture.md) for the Qiskit/QKD boundary, and
[docs/parameters.md](docs/parameters.md) for units and formulas.

Phase 3.6 reconciliation/privacy amplification, Eve, decoy BB84, E91,
dashboards, CLI commands, Aer noise adapters, and advanced transpilation remain
future phases.
