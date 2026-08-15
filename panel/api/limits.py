"""Configurable operational ceilings for the local panel API."""

from __future__ import annotations

import math
from dataclasses import dataclass, fields


@dataclass(frozen=True, slots=True)
class OperationalLimits:
    """Resource ceilings applied synchronously before a job is submitted."""

    max_run_pulses: int = 1_000_000
    max_axis_points: int = 4_096
    max_sweep_evaluations: int = 4_096
    max_total_pulse_events: int = 5_000_000
    max_estimated_quantum_shots: int = 10_000_000
    max_repeats: int = 128
    max_event_sample_size: int = 200
    max_full_event_log_events: int = 20_000
    max_decoy_intensities: int = 32
    max_dynamic_schedules: int = 64
    max_e91_settings: int = 32
    max_protocol_basis_choices: int = 8
    max_time_points: int = 4_096
    max_mean_photon_number: float = 100.0
    max_sweep_payload_bytes: int = 50 * 1024 * 1024
    max_sweep_artifact_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for definition in fields(self):
            value = getattr(self, definition.name)
            if definition.name == "max_mean_photon_number":
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int | float)
                    or not math.isfinite(float(value))
                    or value <= 0.0
                ):
                    raise ValueError(
                        "max_mean_photon_number must be a finite positive number, "
                        f"got {value!r}",
                    )
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(
                    f"{definition.name} must be a positive integer, got {value!r}",
                )


DEFAULT_OPERATIONAL_LIMITS = OperationalLimits()
