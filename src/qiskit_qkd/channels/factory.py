"""Factories for concrete optical channel models."""

from __future__ import annotations

from qiskit_qkd.config import ChannelConfig

from .fiber import FiberChannel
from .ideal import IdealChannel
from .space import FreeSpaceChannel, SpaceChannel, UnderwaterChannel

ConcreteChannel = (
    FiberChannel | FreeSpaceChannel | IdealChannel | SpaceChannel | UnderwaterChannel
)


def channel_from_config(config: ChannelConfig) -> ConcreteChannel:
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
    if kind in {"space", "deep_space", "vacuum"}:
        return SpaceChannel(
            distance_km=config.distance_km,
            wavelength_nm=config.wavelength_nm,
            transmitter_aperture_m=config.transmitter_aperture_m,
            receiver_aperture_m=config.receiver_aperture_m,
            beam_divergence_rad=config.beam_divergence_rad,
            fixed_loss_db=config.fixed_loss_db,
        )
    if kind in {"free_space", "atmospheric", "satellite"}:
        return FreeSpaceChannel(
            distance_km=config.distance_km,
            wavelength_nm=config.wavelength_nm,
            transmitter_aperture_m=config.transmitter_aperture_m,
            receiver_aperture_m=config.receiver_aperture_m,
            beam_divergence_rad=config.beam_divergence_rad,
            fixed_loss_db=config.fixed_loss_db,
            atmospheric_extinction_db_km=config.atmospheric_extinction_db_km,
            scintillation_sigma=config.scintillation_sigma,
            pointing_jitter_rad=config.pointing_jitter_rad,
        )
    if kind in {"underwater", "water", "marine"}:
        return UnderwaterChannel(
            distance_km=config.distance_km,
            wavelength_nm=config.wavelength_nm,
            transmitter_aperture_m=config.transmitter_aperture_m,
            receiver_aperture_m=config.receiver_aperture_m,
            beam_divergence_rad=config.beam_divergence_rad,
            fixed_loss_db=config.fixed_loss_db,
            underwater_extinction_m_inv=config.underwater_extinction_m_inv,
            scintillation_sigma=config.scintillation_sigma,
            pointing_jitter_rad=config.pointing_jitter_rad,
        )
    raise ValueError(f"Unsupported channel kind: {config.kind!r}")
