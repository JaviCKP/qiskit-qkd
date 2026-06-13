"""Classical post-processing helpers for QKD simulations."""

from .classical import (
    BB84SiftedKeys,
    ClassicalPostProcessingResult,
    extract_bb84_sifted_keys,
    run_bb84_classical_postprocessing,
)
from .decoy import estimate_vacuum_weak_decoy_security
from .e91 import (
    chsh_s_from_correlations,
    corrected_e91_bob_key_bit,
    correlation_from_counts,
    e91_key_error,
    setting_pair_label,
)
from .key_rate import bb84_secret_fraction, binary_entropy, qber
from .sifting import sift_bb84_event, sift_bb84_events

__all__ = [
    "BB84SiftedKeys",
    "ClassicalPostProcessingResult",
    "bb84_secret_fraction",
    "binary_entropy",
    "chsh_s_from_correlations",
    "correlation_from_counts",
    "corrected_e91_bob_key_bit",
    "e91_key_error",
    "extract_bb84_sifted_keys",
    "estimate_vacuum_weak_decoy_security",
    "qber",
    "run_bb84_classical_postprocessing",
    "setting_pair_label",
    "sift_bb84_event",
    "sift_bb84_events",
]
