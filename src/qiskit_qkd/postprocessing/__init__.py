"""Classical post-processing helpers for QKD simulations."""

from .classical import (
    BB84SiftedKeys,
    ClassicalPostProcessingResult,
    extract_bb84_sifted_keys,
    run_bb84_classical_postprocessing,
)
from .key_rate import bb84_secret_fraction, binary_entropy, qber
from .sifting import sift_bb84_event, sift_bb84_events

__all__ = [
    "BB84SiftedKeys",
    "ClassicalPostProcessingResult",
    "bb84_secret_fraction",
    "binary_entropy",
    "extract_bb84_sifted_keys",
    "qber",
    "run_bb84_classical_postprocessing",
    "sift_bb84_event",
    "sift_bb84_events",
]
