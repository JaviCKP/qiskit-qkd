"""Detector-state characterization helpers."""

from __future__ import annotations

from dataclasses import dataclass

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import require_non_negative_number
from qiskit_qkd.channels import effective_background_count_rate_hz
from qiskit_qkd.config import Scenario
from qiskit_qkd.temporal import ParameterResolver

from .threshold import ThresholdDetector


@dataclass(frozen=True, slots=True)
class DetectorState:
    """Analytical detector state for one effective scenario."""

    time_s: float
    detector_kind: str
    efficiency: float
    p_dark_per_gate: float
    effective_background_count_rate_hz: float
    p_background_per_gate: float
    dead_time_s: float
    max_count_rate_hz: float | None
    afterpulse_probability: float
    double_click_policy: str
    readout_error_probability: float
    gate_width_s: float

    def to_dict(self) -> JSONObject:
        return {
            "time_s": self.time_s,
            "detector_kind": self.detector_kind,
            "efficiency": self.efficiency,
            "p_dark_per_gate": self.p_dark_per_gate,
            "effective_background_count_rate_hz": (
                self.effective_background_count_rate_hz
            ),
            "p_background_per_gate": self.p_background_per_gate,
            "dead_time_s": self.dead_time_s,
            "max_count_rate_hz": self.max_count_rate_hz,
            "afterpulse_probability": self.afterpulse_probability,
            "double_click_policy": self.double_click_policy,
            "readout_error_probability": self.readout_error_probability,
            "gate_width_s": self.gate_width_s,
        }


def detector_state_from_scenario(
    scenario: Scenario,
    *,
    time_s: float = 0.0,
    resolver: ParameterResolver | None = None,
) -> DetectorState:
    """Return the analytical detector state at ``time_s``."""

    time = require_non_negative_number("time_s", time_s)
    active_resolver = resolver or ParameterResolver()
    effective = active_resolver.scenario_at(scenario, time_s=time)
    return _detector_state_from_effective(effective, time_s=time)


def _detector_state_from_effective(
    scenario: Scenario,
    *,
    time_s: float,
) -> DetectorState:
    detector_config = scenario.detector
    detector = ThresholdDetector(
        efficiency=detector_config.efficiency,
        dark_count_rate_hz=detector_config.dark_count_rate_hz,
        gate_width_s=detector_config.gate_width_s,
        double_click_policy=detector_config.double_click_policy,
        dead_time_s=detector_config.dead_time_s,
        afterpulse_probability=detector_config.afterpulse_probability,
    )
    background_rate_hz = effective_background_count_rate_hz(scenario.channel)
    max_rate = None
    if detector_config.dead_time_s > 0.0:
        max_rate = 1.0 / detector_config.dead_time_s
    return DetectorState(
        time_s=time_s,
        detector_kind=detector_config.kind,
        efficiency=detector_config.efficiency,
        p_dark_per_gate=detector.dark_count_probability,
        effective_background_count_rate_hz=background_rate_hz,
        p_background_per_gate=detector.background_count_probability(
            background_rate_hz,
        ),
        dead_time_s=detector_config.dead_time_s,
        max_count_rate_hz=max_rate,
        afterpulse_probability=detector_config.afterpulse_probability,
        double_click_policy=detector_config.double_click_policy,
        readout_error_probability=detector_config.readout_error_probability,
        gate_width_s=detector_config.gate_width_s,
    )
