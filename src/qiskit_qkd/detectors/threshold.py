"""Threshold detector with efficiency, dark counts, and double-click policy."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from qiskit_qkd._validation import (
    require_bool,
    require_choice,
    require_finite_number,
    require_non_negative_number,
    require_positive_number,
    require_probability,
)

DOUBLE_CLICK_POLICIES = {"discard", "random", "error"}


def _validate_optional_bit(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if value not in {0, 1}:
        raise ValueError(f"{name} must be 0, 1, or None")
    return value


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Detector output projected onto fields stored in an `Event`."""

    detected: bool
    bob_bit: int | None
    detection_origin: str
    detection_pattern: str | None = None
    blocked_by_dead_time: bool = False
    afterpulse: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "detected",
            require_bool("detected", self.detected),
        )
        object.__setattr__(
            self,
            "bob_bit",
            _validate_optional_bit("bob_bit", self.bob_bit),
        )
        object.__setattr__(
            self,
            "blocked_by_dead_time",
            require_bool("blocked_by_dead_time", self.blocked_by_dead_time),
        )
        object.__setattr__(
            self,
            "afterpulse",
            require_bool("afterpulse", self.afterpulse),
        )


@dataclass(slots=True)
class ThresholdDetector:
    """Single threshold detector model for prepare-and-measure BB84.

    `dark_count_rate_hz` and `gate_width_s` define the per-gate probability
    `p_dark = 1 - exp(-dark_count_rate_hz * gate_width_s)`.
    """

    efficiency: float = 1.0
    dark_count_rate_hz: float = 0.0
    gate_width_s: float = 1e-9
    double_click_policy: str = "discard"
    dead_time_s: float = 0.0
    afterpulse_probability: float = 0.0
    _available_at_s: float = field(default=-math.inf, init=False, repr=False)
    _has_prior_detection: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.efficiency = require_probability("efficiency", self.efficiency)
        self.dark_count_rate_hz = require_non_negative_number(
            "dark_count_rate_hz",
            self.dark_count_rate_hz,
        )
        self.gate_width_s = require_positive_number("gate_width_s", self.gate_width_s)
        self.double_click_policy = require_choice(
            "double_click_policy",
            self.double_click_policy,
            DOUBLE_CLICK_POLICIES,
        )
        self.dead_time_s = require_non_negative_number(
            "dead_time_s",
            self.dead_time_s,
        )
        self.afterpulse_probability = require_probability(
            "afterpulse_probability",
            self.afterpulse_probability,
        )

    @property
    def dark_count_probability(self) -> float:
        return 1.0 - math.exp(-self.dark_count_rate_hz * self.gate_width_s)

    def detect(
        self,
        *,
        signal_present: bool,
        measured_bit: int | None,
        rng: random.Random,
        time_s: float | None = None,
    ) -> DetectionResult:
        """Resolve one detection gate using the shared simulation RNG."""

        measured_bit = _validate_optional_bit("measured_bit", measured_bit)
        if signal_present and measured_bit is None:
            raise ValueError("measured_bit is required when signal_present is true")
        detection_time_s = 0.0 if time_s is None else require_finite_number(
            "time_s",
            time_s,
        )
        if self.dead_time_s > 0.0 and detection_time_s < self._available_at_s:
            return DetectionResult(
                detected=False,
                bob_bit=None,
                detection_origin="none",
                detection_pattern="dead_time",
                blocked_by_dead_time=True,
            )

        signal_sample = rng.random()
        signal_click = signal_present and signal_sample < self.efficiency
        dark_click = rng.random() < self.dark_count_probability
        afterpulse_click = (
            not signal_click
            and not dark_click
            and self._has_prior_detection
            and self.afterpulse_probability > 0.0
            and rng.random() < self.afterpulse_probability
        )

        if signal_click and dark_click:
            return self._finalize(
                self._resolve_double_click(measured_bit, rng),
                detection_time_s,
            )
        if signal_click:
            return self._finalize(
                DetectionResult(
                    detected=True,
                    bob_bit=measured_bit,
                    detection_origin="signal",
                    detection_pattern="signal",
                ),
                detection_time_s,
            )
        if dark_click:
            return self._finalize(
                DetectionResult(
                    detected=True,
                    bob_bit=rng.randrange(2),
                    detection_origin="dark",
                    detection_pattern="dark",
                ),
                detection_time_s,
            )
        if afterpulse_click:
            return self._finalize(
                DetectionResult(
                    detected=True,
                    bob_bit=rng.randrange(2),
                    detection_origin="afterpulse",
                    detection_pattern="afterpulse",
                    afterpulse=True,
                ),
                detection_time_s,
            )
        return DetectionResult(
            detected=False,
            bob_bit=None,
            detection_origin="none",
            detection_pattern="no_click",
        )

    def _finalize(
        self,
        result: DetectionResult,
        detection_time_s: float,
    ) -> DetectionResult:
        if result.detected:
            self._has_prior_detection = True
            self._available_at_s = detection_time_s + self.dead_time_s
        return result

    def _resolve_double_click(
        self,
        measured_bit: int | None,
        rng: random.Random,
    ) -> DetectionResult:
        if self.double_click_policy == "discard":
            return DetectionResult(
                detected=False,
                bob_bit=None,
                detection_origin="none",
                detection_pattern="double_click_discard",
            )
        if self.double_click_policy == "random":
            return DetectionResult(
                detected=True,
                bob_bit=rng.randrange(2),
                detection_origin="signal",
                detection_pattern="double_click_random",
            )
        if measured_bit is None:
            bob_bit = rng.randrange(2)
        else:
            bob_bit = 1 - measured_bit
        return DetectionResult(
            detected=True,
            bob_bit=bob_bit,
            detection_origin="signal",
            detection_pattern="double_click_error",
        )
