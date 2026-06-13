"""Quantum execution backends for QKD simulations."""

from .qiskit_sampler import (
    QiskitSamplerBackend,
    backend_from_scenario,
    scenario_requires_aer_noise,
)

__all__ = [
    "QiskitSamplerBackend",
    "backend_from_scenario",
    "scenario_requires_aer_noise",
]
