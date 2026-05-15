"""Ideal lossless channel for baseline QKD simulations."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IdealChannel:
    """Lossless channel with unit transmittance and zero optical loss."""

    @property
    def loss_db(self) -> float:
        return 0.0

    def transmittance(self) -> float:
        """Return the probability that an emitted photon reaches Bob."""

        return 1.0

    def transmit(self, rng: random.Random) -> bool:
        """Return whether a photon survives the channel using the shared RNG."""

        return rng.random() < self.transmittance()
