"""First-order fiber impairment formulas used by event-layer simulations."""

from __future__ import annotations

import math
from typing import Protocol

from qiskit_qkd._validation import require_probability
from qiskit_qkd.config import ChannelConfig, Scenario

PS_TO_S = 1e-12
NS_TO_S = 1e-9


class TransmittanceLike(Protocol):
    def transmittance(self) -> float:
        """Return the base channel transmittance before state-dependent loss."""


def pmd_broadening_s(channel: ChannelConfig) -> float:
    """Return RMS-like PMD temporal spreading in seconds.

    The first-order model uses ``sigma_pmd = D_pmd * sqrt(L)`` with ``D_pmd`` in
    ps/sqrt(km) and distance ``L`` in km.
    """

    return channel.pmd_coefficient_ps_sqrt_km * math.sqrt(channel.distance_km) * PS_TO_S


def chromatic_broadening_s(channel: ChannelConfig) -> float:
    """Return chromatic-dispersion temporal spreading in seconds.

    ``source_spectral_width_nm`` is interpreted as the spectral width used for
    the same temporal-width convention as the timing jitter.
    """

    return (
        abs(channel.chromatic_dispersion_ps_nm_km)
        * channel.distance_km
        * channel.source_spectral_width_nm
        * PS_TO_S
    )


def temporal_broadening_s(channel: ChannelConfig) -> float:
    """Combine PMD and chromatic dispersion as independent Gaussian widths."""

    return math.hypot(
        pmd_broadening_s(channel),
        chromatic_broadening_s(channel),
        scattering_broadening_s(channel),
    )


def scattering_broadening_s(channel: ChannelConfig) -> float:
    """Return underwater scattering temporal spreading in seconds.

    ``underwater_scattering_broadening_ns_per_m`` is a first-order pulse-tail
    width per meter of water path. It is kept as a Gaussian-equivalent width so
    it can combine cleanly with the existing timing jitter model.
    """

    distance_m = channel.distance_km * 1_000.0
    return (
        channel.underwater_scattering_broadening_ns_per_m
        * distance_m
        * NS_TO_S
    )


def effective_jitter_std_s(scenario: Scenario) -> float:
    """Return detector timing jitter including channel temporal broadening."""

    return math.hypot(
        scenario.timing.jitter_std_s,
        temporal_broadening_s(scenario.channel),
    )


def pdl_transmittance_factor(
    channel: ChannelConfig,
    *,
    alice_bit: int | None = None,
    alice_basis: str | None = None,
) -> float:
    """Return multiplicative polarization-dependent-loss factor.

    The favored eigenstate keeps the base channel transmittance. The orthogonal
    eigenstate receives the configured PDL attenuation, and conjugate BB84
    states use the mean eigenmode transmission. This keeps PDL as extra loss;
    it never boosts the channel above the ordinary fiber transmittance.
    """

    if channel.polarization_dependent_loss_db == 0.0:
        return 1.0
    if alice_bit is None or alice_basis is None:
        return 1.0
    if (
        not isinstance(alice_bit, int)
        or isinstance(alice_bit, bool)
        or alice_bit not in {0, 1}
    ):
        raise ValueError("alice_bit must be 0, 1, or None")

    min_factor = 10 ** (-channel.polarization_dependent_loss_db / 10.0)
    basis = alice_basis.strip().upper()
    if basis != channel.pdl_axis_basis:
        return (1.0 + min_factor) / 2.0
    if alice_bit == channel.pdl_axis_bit:
        return 1.0
    return min_factor


def pdl_min_transmittance(channel: TransmittanceLike, config: ChannelConfig) -> float:
    """Return the weaker PDL eigenmode transmittance for characterization rows."""

    base = require_probability("channel.transmittance", channel.transmittance())
    factor = 10 ** (-config.polarization_dependent_loss_db / 10.0)
    return base * factor


def raman_count_rate_hz(channel: ChannelConfig) -> float:
    """Return Raman crosstalk count rate entering Bob's optical filter."""

    filter_factor = 10 ** (-channel.raman_filter_isolation_db / 10.0)
    return (
        channel.raman_coefficient_hz_mw_km
        * channel.classical_channel_power_mw
        * channel.distance_km
        * filter_factor
    )


def effective_background_count_rate_hz(channel: ChannelConfig) -> float:
    """Return detector background rate after adding Raman crosstalk."""

    return channel.background_count_rate_hz + raman_count_rate_hz(channel)
