"""Qiskit-first tools for quantum key distribution simulations."""

from typing import TYPE_CHECKING

from ._version import __version__
from .config import (
    ChannelConfig,
    DetectorConfig,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
)
from .reproducibility import make_rng
from .results import Event, Metrics, SimulationResult

if TYPE_CHECKING:
    from .backends import QiskitSamplerBackend
    from .protocols import BB84Protocol
    from .qiskit_integration import CircuitFactory

__all__ = [
    "BB84Protocol",
    "ChannelConfig",
    "CircuitFactory",
    "DetectorConfig",
    "Event",
    "Metrics",
    "PostProcessingConfig",
    "ProtocolConfig",
    "QiskitSamplerBackend",
    "Scenario",
    "SimulationResult",
    "SourceConfig",
    "__version__",
    "make_rng",
]


def __getattr__(name: str) -> object:
    if name == "BB84Protocol":
        from .protocols import BB84Protocol

        return BB84Protocol
    if name == "CircuitFactory":
        from .qiskit_integration import CircuitFactory

        return CircuitFactory
    if name == "QiskitSamplerBackend":
        from .backends import QiskitSamplerBackend

        return QiskitSamplerBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
