# qiskit-qkd

`qiskit-qkd` is a Qiskit-first Python package for quantum key distribution
simulations. The repository is currently in Phase 0: technical preparation,
packaging, and baseline reading.

No protocol simulation is implemented in this phase. The first functional
example belongs to Phase 2, after the minimal domain model and BB84 circuit
path exist.

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

## Smoke Execution

```powershell
python -c "import qiskit_qkd; print(qiskit_qkd.__version__)"
```

See [docs/development.md](docs/development.md) for the Phase 0 scope, reading
baseline, and command reference.
