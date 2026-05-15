"""Fiber attenuation model for QKD photon survival events."""

from __future__ import annotations

import random
from dataclasses import dataclass

from qiskit_qkd._validation import require_non_negative_number


@dataclass(frozen=True, slots=True)
class FiberChannel:
    """Single-span fiber channel.

    Distances are in kilometers and attenuation is in dB/km. Photon loss is
    modeled as event-level no-click probability, not as amplitude damping on a
    qubit state.
    """

    distance_km: float
    attenuation_db_km: float = 0.2
    fixed_loss_db: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "distance_km",
            require_non_negative_number("distance_km", self.distance_km),
        )
        object.__setattr__(
            self,
            "attenuation_db_km",
            require_non_negative_number(
                "attenuation_db_km",
                self.attenuation_db_km,
            ),
        )
        object.__setattr__(
            self,
            "fixed_loss_db",
            require_non_negative_number("fixed_loss_db", self.fixed_loss_db),
        )

    @property
    def loss_db(self) -> float:
        return self.attenuation_db_km * self.distance_km + self.fixed_loss_db

    def transmittance(self) -> float:
        """Return eta_channel = 10 ** (-loss_db / 10)."""

        return 10 ** (-self.loss_db / 10)

    def transmit(self, rng: random.Random) -> bool:
        """Return whether a photon survives fiber attenuation."""

        return rng.random() < self.transmittance()
