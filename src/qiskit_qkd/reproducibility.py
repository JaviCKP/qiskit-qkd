"""Centralized seed handling for deterministic simulations."""

from __future__ import annotations

import random

from ._validation import require_non_negative_int


def make_rng(seed: int) -> random.Random:
    """Return a deterministic Python RNG initialized from a validated seed."""

    return random.Random(require_non_negative_int("seed", seed))


def sample_unit_interval(seed: int, count: int) -> tuple[float, ...]:
    """Return deterministic samples used by reproducibility smoke checks."""

    rng = make_rng(seed)
    sample_count = require_non_negative_int("count", count)
    return tuple(rng.random() for _ in range(sample_count))
