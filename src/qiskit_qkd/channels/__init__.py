"""Physical channel models for QKD event simulations."""

from __future__ import annotations

from .characterization import (
    ChannelCharacterizer,
    ChannelState,
    channel_state_from_scenario,
)
from .factory import ConcreteChannel, channel_from_config
from .fiber import FiberChannel
from .ideal import IdealChannel
from .impairments import (
    chromatic_broadening_s,
    effective_background_count_rate_hz,
    effective_jitter_std_s,
    pdl_transmittance_factor,
    pmd_broadening_s,
    raman_count_rate_hz,
    scattering_broadening_s,
    temporal_broadening_s,
)
from .space import FreeSpaceChannel, SpaceChannel, UnderwaterChannel

__all__ = [
    "ChannelCharacterizer",
    "ChannelState",
    "ConcreteChannel",
    "FiberChannel",
    "FreeSpaceChannel",
    "IdealChannel",
    "SpaceChannel",
    "UnderwaterChannel",
    "channel_from_config",
    "channel_state_from_scenario",
    "chromatic_broadening_s",
    "effective_background_count_rate_hz",
    "effective_jitter_std_s",
    "pdl_transmittance_factor",
    "pmd_broadening_s",
    "raman_count_rate_hz",
    "scattering_broadening_s",
    "temporal_broadening_s",
]
