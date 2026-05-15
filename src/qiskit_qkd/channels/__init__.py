"""Physical channel models for QKD event simulations."""

from __future__ import annotations

from qiskit_qkd.config import ChannelConfig

from .fiber import FiberChannel
from .ideal import IdealChannel

__all__ = ["FiberChannel", "IdealChannel", "channel_from_config"]


def channel_from_config(config: ChannelConfig) -> FiberChannel | IdealChannel:
    """Build a concrete channel model from validated scenario configuration."""

    kind = config.kind.lower()
    if kind == "fiber":
        return FiberChannel(
            distance_km=config.distance_km,
            attenuation_db_km=config.attenuation_db_km,
            fixed_loss_db=config.fixed_loss_db,
        )
    if kind == "ideal":
        return IdealChannel()
    raise ValueError(f"Unsupported channel kind: {config.kind!r}")
