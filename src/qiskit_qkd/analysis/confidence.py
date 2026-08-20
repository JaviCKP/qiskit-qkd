"""Confidence intervals used by sweep and metric summaries.

The implementation intentionally has no optional numerical dependency.  Wilson
intervals are used for binomial proportions backed by counters, while means of
independent repeat values use a two-sided Student *t* interval.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any

DEFAULT_CONFIDENCE_LEVEL = 0.95


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    """A serializable confidence interval.

    ``bounds`` is ``(lower, upper)``.  Both values are ``None`` when the
    requested estimate is undefined (for example, a zero denominator or fewer
    than two repeats for a mean).  ``lower`` and ``upper`` properties are
    provided as convenient aliases without changing the stable serialized
    shape.
    """

    level: float
    method: str
    n: int
    bounds: tuple[float | None, float | None]

    def __post_init__(self) -> None:
        _validate_level(self.level)
        if not isinstance(self.method, str) or not self.method:
            raise ValueError("confidence interval method must be a non-empty string")
        if not isinstance(self.n, int) or isinstance(self.n, bool) or self.n < 0:
            raise ValueError("confidence interval n must be a non-negative integer")
        if (
            not isinstance(self.bounds, tuple)
            or len(self.bounds) != 2
            or any(
                bound is not None
                and (
                    isinstance(bound, bool)
                    or not isinstance(bound, int | float)
                    or not math.isfinite(float(bound))
                )
                for bound in self.bounds
            )
        ):
            raise ValueError(
                "confidence interval bounds must be finite numbers or None",
            )
        if self.bounds[0] is None and self.bounds[1] is not None:
            raise ValueError(
                "confidence interval bounds must be both defined or undefined",
            )
        if self.bounds[0] is not None and self.bounds[1] is None:
            raise ValueError(
                "confidence interval bounds must be both defined or undefined",
            )
        if self.bounds[0] is not None and self.bounds[0] > self.bounds[1]:
            raise ValueError(
                "confidence interval lower bound must not exceed upper bound",
            )

    @property
    def lower(self) -> float | None:
        return self.bounds[0]

    @property
    def upper(self) -> float | None:
        return self.bounds[1]

    @property
    def defined(self) -> bool:
        return self.lower is not None

    def to_dict(self) -> dict[str, Any]:
        """Return the stable JSON-safe representation used in summary rows."""

        return {
            "level": self.level,
            "method": self.method,
            "n": self.n,
            "bounds": [self.lower, self.upper],
        }


def wilson_interval(
    successes: int,
    trials: int,
    *,
    level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> ConfidenceInterval:
    """Return a Wilson score interval for ``successes / trials``.

    A zero trial count is represented explicitly as an undefined interval,
    rather than as ``0 ± 0``.  The resulting bounds are always clipped to the
    probability domain ``[0, 1]``.
    """

    _validate_level(level)
    _validate_count("successes", successes)
    _validate_count("trials", trials)
    if successes > trials:
        raise ValueError("successes must not exceed trials")
    if trials == 0:
        return ConfidenceInterval(level, "wilson", 0, (None, None))

    z = NormalDist().inv_cdf(0.5 + level / 2.0)
    proportion = successes / trials
    z_squared = z * z
    denominator = 1.0 + z_squared / trials
    centre = (proportion + z_squared / (2.0 * trials)) / denominator
    half_width = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / trials
            + z_squared / (4.0 * trials * trials),
        )
        / denominator
    )
    lower = max(0.0, centre - half_width)
    upper = min(1.0, centre + half_width)
    return ConfidenceInterval(level, "wilson", trials, (lower, upper))


def t_interval(
    values: Iterable[int | float],
    *,
    level: float = DEFAULT_CONFIDENCE_LEVEL,
) -> ConfidenceInterval:
    """Return a two-sided Student *t* interval for a repeat mean.

    One observation has no estimate of sample variance and is therefore
    explicitly undefined.  Values must be finite; ``n`` is the count of values
    actually used in the interval.
    """

    _validate_level(level)
    observations = [float(value) for value in values]
    if any(not math.isfinite(value) for value in observations):
        raise ValueError("confidence interval values must be finite")
    n = len(observations)
    if n < 2:
        return ConfidenceInterval(level, "t", n, (None, None))
    mean = math.fsum(observations) / n
    variance = math.fsum((value - mean) ** 2 for value in observations) / (n - 1)
    standard_error = math.sqrt(variance / n)
    critical = _student_t_critical(level, n - 1)
    half_width = critical * standard_error
    return ConfidenceInterval(level, "t", n, (mean - half_width, mean + half_width))


# Discoverable aliases for callers that prefer noun-first naming.
proportion_confidence_interval = wilson_interval
mean_confidence_interval = t_interval
t_confidence_interval = t_interval


def _validate_level(level: float) -> None:
    if (
        isinstance(level, bool)
        or not isinstance(level, int | float)
        or not math.isfinite(float(level))
        or not 0.0 < float(level) < 1.0
    ):
        raise ValueError("confidence level must be finite and strictly between 0 and 1")


def _validate_count(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _student_t_critical(level: float, degrees_of_freedom: int) -> float:
    """Invert the Student *t* CDF with a monotone bisection search."""

    target = 0.5 + level / 2.0
    lower = 0.0
    upper = 1.0
    while _student_t_cdf(upper, degrees_of_freedom) < target:
        upper *= 2.0
    for _ in range(90):
        middle = (lower + upper) / 2.0
        if _student_t_cdf(middle, degrees_of_freedom) < target:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2.0


def _student_t_cdf(value: float, degrees_of_freedom: int) -> float:
    if value == 0.0:
        return 0.5
    x = degrees_of_freedom / (degrees_of_freedom + value * value)
    tail = 0.5 * _regularized_beta(x, degrees_of_freedom / 2.0, 0.5)
    return 1.0 - tail if value > 0.0 else tail


def _regularized_beta(x: float, a: float, b: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_factor = (
        a * math.log(x)
        + b * math.log1p(-x)
        - math.lgamma(a)
        - math.lgamma(b)
        + math.lgamma(a + b)
    )
    factor = math.exp(log_factor)
    if x < (a + 1.0) / (a + b + 2.0):
        return factor * _beta_continued_fraction(a, b, x) / a
    return 1.0 - factor * _beta_continued_fraction(b, a, 1.0 - x) / b


def _beta_continued_fraction(a: float, b: float, x: float) -> float:
    tiny = 1e-300
    epsilon = 3e-14
    maximum_iterations = 200
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = tiny if abs(d) < tiny else d
    d = 1.0 / d
    result = d
    for iteration in range(1, maximum_iterations + 1):
        doubled = 2.0 * iteration
        numerator = iteration * (b - iteration) * x
        denominator = (qam + doubled) * (a + doubled)
        delta = numerator / denominator
        d = 1.0 + delta * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + delta / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        result *= d * c
        numerator = -(a + iteration) * (qab + iteration) * x
        denominator = (a + doubled) * (qap + doubled)
        delta = numerator / denominator
        d = 1.0 + delta * d
        d = tiny if abs(d) < tiny else d
        c = 1.0 + delta / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        correction = d * c
        result *= correction
        if abs(correction - 1.0) < epsilon:
            break
    return result
