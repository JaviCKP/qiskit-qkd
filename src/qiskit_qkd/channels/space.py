"""Free-space, deep-space, and underwater optical channel models."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from qiskit_qkd._validation import (
    require_non_negative_number,
    require_positive_number,
    require_probability,
)


@dataclass(frozen=True, slots=True)
class SpaceChannel:
    """Diffraction-limited vacuum optical link.

    The event-layer loss is modeled as geometric beam-spreading loss plus fixed
    optical loss. Vacuum propagation does not add atmospheric extinction or
    stochastic fading in this first-order model.
    """

    distance_km: float
    wavelength_nm: float = 850.0
    transmitter_aperture_m: float = 0.10
    receiver_aperture_m: float = 0.50
    beam_divergence_rad: float = 0.0
    fixed_loss_db: float = 0.0

    def __post_init__(self) -> None:
        _validate_common_link(self)

    @property
    def divergence_rad(self) -> float:
        """Return configured divergence, or the Airy-disk estimate."""

        if self.beam_divergence_rad > 0.0:
            return self.beam_divergence_rad
        wavelength_m = self.wavelength_nm * 1e-9
        return 2.44 * wavelength_m / self.transmitter_aperture_m

    @property
    def beam_diameter_m(self) -> float:
        """Return a first-order beam diameter at the receiver plane."""

        return self.transmitter_aperture_m + self.divergence_rad * _distance_m(self)

    @property
    def beam_radius_m(self) -> float:
        """Return a first-order beam radius at the receiver plane."""

        return self.beam_diameter_m / 2.0

    @property
    def geometric_transmittance(self) -> float:
        """Return aperture-coupling transmittance from beam spreading."""

        if self.distance_km == 0.0 and self.receiver_aperture_m >= self.beam_diameter_m:
            return 1.0
        eta = (self.receiver_aperture_m / self.beam_diameter_m) ** 2
        return _clip_probability(eta)

    @property
    def loss_db(self) -> float:
        eta = max(self.transmittance(), 1e-300)
        return -10.0 * math.log10(eta)

    def transmittance(self) -> float:
        """Return deterministic baseline photon survival probability."""

        return _clip_probability(
            self.geometric_transmittance * _db_transmittance(self.fixed_loss_db),
        )

    def sample_transmittance(self, rng: random.Random) -> float:
        """Return instantaneous photon survival probability for one pulse."""

        return self.transmittance()

    def transmit(self, rng: random.Random) -> bool:
        """Return whether one photon survives the link."""

        return rng.random() < self.sample_transmittance(rng)


@dataclass(frozen=True, slots=True)
class FreeSpaceChannel(SpaceChannel):
    """Atmospheric or satellite-to-ground optical link.

    The baseline loss combines geometric spreading, atmospheric extinction, and
    fixed optics. ``sample_transmittance`` adds optional mean-one log-normal
    scintillation and Rayleigh pointing jitter per pulse.
    """

    atmospheric_extinction_db_km: float = 0.0
    scintillation_sigma: float = 0.0
    pointing_jitter_rad: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(
            self,
            "atmospheric_extinction_db_km",
            require_non_negative_number(
                "atmospheric_extinction_db_km",
                self.atmospheric_extinction_db_km,
            ),
        )
        object.__setattr__(
            self,
            "scintillation_sigma",
            require_non_negative_number(
                "scintillation_sigma",
                self.scintillation_sigma,
            ),
        )
        object.__setattr__(
            self,
            "pointing_jitter_rad",
            require_non_negative_number(
                "pointing_jitter_rad",
                self.pointing_jitter_rad,
            ),
        )

    @property
    def atmospheric_loss_db(self) -> float:
        return self.atmospheric_extinction_db_km * self.distance_km

    def transmittance(self) -> float:
        """Return clear-air baseline survival probability before fading."""

        return _clip_probability(
            self.geometric_transmittance
            * _db_transmittance(self.fixed_loss_db + self.atmospheric_loss_db),
        )

    def sample_transmittance(self, rng: random.Random) -> float:
        """Return a pulse-level survival probability with fading."""

        eta = self.transmittance()
        eta *= _mean_one_lognormal(rng, self.scintillation_sigma)
        eta *= _pointing_factor(
            rng,
            pointing_jitter_rad=self.pointing_jitter_rad,
            distance_m=_distance_m(self),
            beam_radius_m=self.beam_radius_m,
        )
        return _clip_probability(eta)


@dataclass(frozen=True, slots=True)
class UnderwaterChannel(SpaceChannel):
    """Underwater optical link with Beer-Lambert extinction.

    Distances stay in kilometers for consistency with the rest of the repo, but
    water extinction is configured in inverse meters because underwater links
    are usually characterized over tens or hundreds of meters.
    """

    underwater_extinction_m_inv: float = 0.0
    scintillation_sigma: float = 0.0
    pointing_jitter_rad: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(
            self,
            "underwater_extinction_m_inv",
            require_non_negative_number(
                "underwater_extinction_m_inv",
                self.underwater_extinction_m_inv,
            ),
        )
        object.__setattr__(
            self,
            "scintillation_sigma",
            require_non_negative_number(
                "scintillation_sigma",
                self.scintillation_sigma,
            ),
        )
        object.__setattr__(
            self,
            "pointing_jitter_rad",
            require_non_negative_number(
                "pointing_jitter_rad",
                self.pointing_jitter_rad,
            ),
        )

    @property
    def water_extinction_factor(self) -> float:
        return math.exp(-self.underwater_extinction_m_inv * _distance_m(self))

    def transmittance(self) -> float:
        """Return baseline Beer-Lambert and geometric survival probability."""

        return _clip_probability(
            self.geometric_transmittance
            * self.water_extinction_factor
            * _db_transmittance(self.fixed_loss_db),
        )

    def sample_transmittance(self, rng: random.Random) -> float:
        """Return a pulse-level survival probability with water fading."""

        eta = self.transmittance()
        eta *= _mean_one_lognormal(rng, self.scintillation_sigma)
        eta *= _pointing_factor(
            rng,
            pointing_jitter_rad=self.pointing_jitter_rad,
            distance_m=_distance_m(self),
            beam_radius_m=self.beam_radius_m,
        )
        return _clip_probability(eta)


def _validate_common_link(channel: SpaceChannel) -> None:
    object.__setattr__(
        channel,
        "distance_km",
        require_non_negative_number("distance_km", channel.distance_km),
    )
    object.__setattr__(
        channel,
        "wavelength_nm",
        require_positive_number("wavelength_nm", channel.wavelength_nm),
    )
    object.__setattr__(
        channel,
        "transmitter_aperture_m",
        require_positive_number(
            "transmitter_aperture_m",
            channel.transmitter_aperture_m,
        ),
    )
    object.__setattr__(
        channel,
        "receiver_aperture_m",
        require_positive_number("receiver_aperture_m", channel.receiver_aperture_m),
    )
    object.__setattr__(
        channel,
        "beam_divergence_rad",
        require_non_negative_number(
            "beam_divergence_rad",
            channel.beam_divergence_rad,
        ),
    )
    object.__setattr__(
        channel,
        "fixed_loss_db",
        require_non_negative_number("fixed_loss_db", channel.fixed_loss_db),
    )


def _distance_m(channel: SpaceChannel) -> float:
    return channel.distance_km * 1_000.0


def _db_transmittance(loss_db: float) -> float:
    return 10 ** (-loss_db / 10.0)


def _mean_one_lognormal(rng: random.Random, sigma: float) -> float:
    if sigma == 0.0:
        return 1.0
    return rng.lognormvariate(-0.5 * sigma * sigma, sigma)


def _pointing_factor(
    rng: random.Random,
    *,
    pointing_jitter_rad: float,
    distance_m: float,
    beam_radius_m: float,
) -> float:
    if pointing_jitter_rad == 0.0 or distance_m == 0.0:
        return 1.0
    sigma_m = pointing_jitter_rad * distance_m
    radial_offset_m = sigma_m * math.sqrt(-2.0 * math.log1p(-rng.random()))
    return math.exp(-2.0 * (radial_offset_m / beam_radius_m) ** 2)


def _clip_probability(value: float) -> float:
    return require_probability("transmittance", min(1.0, max(0.0, value)))
