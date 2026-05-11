"""Qiskit-first tools for quantum key distribution simulations."""

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

__all__ = [
    "ChannelConfig",
    "DetectorConfig",
    "Event",
    "Metrics",
    "PostProcessingConfig",
    "ProtocolConfig",
    "Scenario",
    "SimulationResult",
    "SourceConfig",
    "__version__",
    "make_rng",
]
