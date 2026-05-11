"""Classical post-processing helpers for QKD simulations."""

from .key_rate import bb84_secret_fraction, binary_entropy, qber
from .sifting import sift_bb84_event, sift_bb84_events

__all__ = [
    "bb84_secret_fraction",
    "binary_entropy",
    "qber",
    "sift_bb84_event",
    "sift_bb84_events",
]
