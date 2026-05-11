"""Aggregate metrics for QKD simulation results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    reject_unknown_fields,
    require_bool,
    require_non_negative_int,
    require_non_negative_number,
    require_probability,
)


@dataclass(frozen=True, slots=True)
class Metrics:
    """Aggregate counters and rates for a completed or placeholder run."""

    pulses: int
    emitted: int = 0
    transmitted: int = 0
    detected: int = 0
    sifted: int = 0
    errors: int = 0
    qber: float = 0.0
    loss_db: float = 0.0
    gain: float = 0.0
    raw_detection_rate_hz: float = 0.0
    sifted_key_rate_bps: float = 0.0
    secret_key_rate_bps: float = 0.0
    abort: bool = False
    eve_intercepted_fraction: float = 0.0
    eve_information_estimate: float = 0.0
    chsh_s: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pulses",
            require_non_negative_int("pulses", self.pulses),
        )
        for name in ("emitted", "transmitted", "detected", "sifted", "errors"):
            value = require_non_negative_int(name, getattr(self, name))
            if value > self.pulses:
                raise ValueError(f"{name} must not exceed pulses")
            object.__setattr__(self, name, value)
        if self.transmitted > self.emitted:
            raise ValueError("transmitted must not exceed emitted")
        if self.errors > self.sifted:
            raise ValueError("errors must not exceed sifted")
        object.__setattr__(self, "qber", require_probability("qber", self.qber))
        object.__setattr__(
            self,
            "loss_db",
            require_non_negative_number("loss_db", self.loss_db),
        )
        object.__setattr__(self, "gain", require_probability("gain", self.gain))
        for name in (
            "raw_detection_rate_hz",
            "sifted_key_rate_bps",
            "secret_key_rate_bps",
        ):
            object.__setattr__(
                self,
                name,
                require_non_negative_number(name, getattr(self, name)),
            )
        object.__setattr__(self, "abort", require_bool("abort", self.abort))
        object.__setattr__(
            self,
            "eve_intercepted_fraction",
            require_probability(
                "eve_intercepted_fraction",
                self.eve_intercepted_fraction,
            ),
        )
        object.__setattr__(
            self,
            "eve_information_estimate",
            require_probability(
                "eve_information_estimate",
                self.eve_information_estimate,
            ),
        )
        if self.chsh_s is not None:
            chsh_s = require_non_negative_number("chsh_s", self.chsh_s)
            if chsh_s > 4:
                raise ValueError("chsh_s must not exceed 4")
            object.__setattr__(self, "chsh_s", chsh_s)

    def to_dict(self) -> JSONObject:
        return {
            "pulses": self.pulses,
            "emitted": self.emitted,
            "transmitted": self.transmitted,
            "detected": self.detected,
            "sifted": self.sifted,
            "errors": self.errors,
            "qber": self.qber,
            "loss_db": self.loss_db,
            "gain": self.gain,
            "raw_detection_rate_hz": self.raw_detection_rate_hz,
            "sifted_key_rate_bps": self.sifted_key_rate_bps,
            "secret_key_rate_bps": self.secret_key_rate_bps,
            "abort": self.abort,
            "eve_intercepted_fraction": self.eve_intercepted_fraction,
            "eve_information_estimate": self.eve_information_estimate,
            "chsh_s": self.chsh_s,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        reject_unknown_fields(
            "Metrics",
            data,
            {
                "pulses",
                "emitted",
                "transmitted",
                "detected",
                "sifted",
                "errors",
                "qber",
                "loss_db",
                "gain",
                "raw_detection_rate_hz",
                "sifted_key_rate_bps",
                "secret_key_rate_bps",
                "abort",
                "eve_intercepted_fraction",
                "eve_information_estimate",
                "chsh_s",
            },
        )
        return cls(
            pulses=data["pulses"],
            emitted=data.get("emitted", 0),
            transmitted=data.get("transmitted", 0),
            detected=data.get("detected", 0),
            sifted=data.get("sifted", 0),
            errors=data.get("errors", 0),
            qber=data.get("qber", 0.0),
            loss_db=data.get("loss_db", 0.0),
            gain=data.get("gain", 0.0),
            raw_detection_rate_hz=data.get("raw_detection_rate_hz", 0.0),
            sifted_key_rate_bps=data.get("sifted_key_rate_bps", 0.0),
            secret_key_rate_bps=data.get("secret_key_rate_bps", 0.0),
            abort=data.get("abort", False),
            eve_intercepted_fraction=data.get("eve_intercepted_fraction", 0.0),
            eve_information_estimate=data.get("eve_information_estimate", 0.0),
            chsh_s=data.get("chsh_s"),
        )
