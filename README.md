# qiskit-qkd

`qiskit-qkd` is a Qiskit-first Python package for quantum key distribution
simulations. It currently includes the validated domain model plus a minimal
ideal BB84 path backed by real Qiskit circuits and Sampler primitives.

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

## Smoke Execution

```powershell
python -c "import qiskit_qkd; print(qiskit_qkd.__version__)"
```

See [docs/development.md](docs/development.md) for the development command
reference. See [docs/domain_model.md](docs/domain_model.md) for the data model,
[docs/architecture.md](docs/architecture.md) for the Qiskit/QKD boundary, and
[docs/parameters.md](docs/parameters.md) for units and formulas.
