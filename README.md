# qiskit-qkd

`qiskit-qkd` is a Qiskit-first Python package for quantum key distribution
simulations. The repository is currently in Phase 1: minimal domain model,
validation, JSON serialization, and reproducible seed handling.

No protocol simulation is implemented yet. The first functional example belongs
to Phase 2, after the BB84 Qiskit circuit path exists.

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

See [docs/development.md](docs/development.md) for the development command
reference. See [docs/domain_model.md](docs/domain_model.md) for the Phase 1
data model.
