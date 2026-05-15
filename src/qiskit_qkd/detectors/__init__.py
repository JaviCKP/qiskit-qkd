"""Detector models for QKD event simulations."""

from __future__ import annotations

from qiskit_qkd.config import DetectorConfig

from .threshold import DetectionResult, ThresholdDetector

__all__ = ["DetectionResult", "ThresholdDetector", "detector_from_config"]


def detector_from_config(config: DetectorConfig) -> ThresholdDetector:
    """Build a threshold detector from validated scenario configuration."""

    kind = config.kind.lower()
    if kind in {"ideal", "threshold"}:
        return ThresholdDetector(
            efficiency=config.efficiency,
            dark_count_rate_hz=config.dark_count_rate_hz,
            gate_width_s=config.gate_width_s,
            double_click_policy=config.double_click_policy,
            dead_time_s=config.dead_time_s,
            afterpulse_probability=config.afterpulse_probability,
        )
    raise ValueError(f"Unsupported detector kind: {config.kind!r}")
