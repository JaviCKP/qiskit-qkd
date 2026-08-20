"""Threshold detector with efficiency, dark counts, and double-click policy."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from qiskit_qkd._validation import (
    require_bool,
    require_choice,
    require_finite_number,
    require_non_negative_int,
    require_non_negative_number,
    require_positive_number,
    require_probability,
)

DOUBLE_CLICK_POLICIES = {"discard", "random", "error"}
TIME_COMPARISON_TOLERANCE_S = 1e-15


def _validate_optional_bit(name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value not in {0, 1}:
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
    detector_fired: bool = False

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
        object.__setattr__(
            self,
            "detector_fired",
            require_bool("detector_fired", self.detector_fired),
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
    afterpulse_tau_s: float | None = None
    _available_at_s: float = field(default=-math.inf, init=False, repr=False)
    _last_detection_time_s: float | None = field(default=None, init=False, repr=False)

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
        if self.afterpulse_tau_s is not None:
            self.afterpulse_tau_s = require_finite_number(
                "afterpulse_tau_s",
                self.afterpulse_tau_s,
            )
            if self.afterpulse_tau_s <= 0.0:
                raise ValueError("afterpulse_tau_s must be positive or None")

    @property
    def dark_count_probability(self) -> float:
        return 1.0 - math.exp(-self.dark_count_rate_hz * self.gate_width_s)

    def background_count_probability(self, background_count_rate_hz: float) -> float:
        background_count_rate_hz = require_non_negative_number(
            "background_count_rate_hz",
            background_count_rate_hz,
        )
        return 1.0 - math.exp(-background_count_rate_hz * self.gate_width_s)

    def detect(
        self,
        *,
        signal_present: bool,
        signal_photon_number: int | None = None,
        measured_bit: int | None,
        rng: random.Random,
        time_s: float | None = None,
        background_count_rate_hz: float = 0.0,
    ) -> DetectionResult:
        """Resolve one detection gate using the shared simulation RNG."""

        measured_bit = _validate_optional_bit("measured_bit", measured_bit)
        background_count_rate_hz = require_non_negative_number(
            "background_count_rate_hz",
            background_count_rate_hz,
        )
        if signal_photon_number is None:
            signal_photon_number = 1 if signal_present else 0
        signal_photon_number = require_non_negative_int(
            "signal_photon_number",
            signal_photon_number,
        )
        if signal_present and signal_photon_number == 0:
            raise ValueError("signal_photon_number must be positive for a signal")
        if not signal_present and signal_photon_number != 0:
            raise ValueError("signal_photon_number must be zero without a signal")
        if signal_present and measured_bit is None:
            raise ValueError("measured_bit is required when signal_present is true")
        detection_time_s = 0.0 if time_s is None else require_finite_number(
            "time_s",
            time_s,
        )
        if (
            self.dead_time_s > 0.0
            and detection_time_s < self._available_at_s - TIME_COMPARISON_TOLERANCE_S
        ):
            return DetectionResult(
                detected=False,
                bob_bit=None,
                detection_origin="none",
                detection_pattern="dead_time",
                blocked_by_dead_time=True,
        )

        signal_click_probability = (
            1.0 - (1.0 - self.efficiency) ** signal_photon_number
        )
        signal_sample = rng.random()
        signal_click = signal_present and signal_sample < signal_click_probability
        dark_probability = self.dark_count_probability
        dark_click = dark_probability > 0.0 and rng.random() < dark_probability
        background_click = (
            background_count_rate_hz > 0.0
            and rng.random()
            < self.background_count_probability(background_count_rate_hz)
        )
        afterpulse_probability = self._afterpulse_probability(detection_time_s)
        afterpulse_click = (
            not signal_click
            and not dark_click
            and not background_click
            and self._last_detection_time_s is not None
            and afterpulse_probability > 0.0
            and rng.random() < afterpulse_probability
        )

        if signal_click and (dark_click or background_click):
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
        if background_click:
            return self._finalize(
                DetectionResult(
                    detected=True,
                    bob_bit=rng.randrange(2),
                    detection_origin="background",
                    detection_pattern="background",
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
        if result.detected or result.detector_fired:
            self._last_detection_time_s = detection_time_s
            self._available_at_s = detection_time_s + self.dead_time_s
        return result

    def _afterpulse_probability(self, detection_time_s: float) -> float:
        """Return the afterpulse probability for this gate.

        With no time constant this deliberately returns the legacy constant
        per-gate probability.  Otherwise the previous detector firing time is
        used and the exponential is clamped to ``[0, p0]`` for numerical and
        out-of-order timestamp safety.
        """

        p0 = self.afterpulse_probability
        if p0 == 0.0 or self._last_detection_time_s is None:
            return 0.0
        if self.afterpulse_tau_s is None:
            return p0
        delta_t = max(0.0, detection_time_s - self._last_detection_time_s)
        return min(1.0, max(0.0, p0 * math.exp(-delta_t / self.afterpulse_tau_s)))

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
                detector_fired=True,
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
