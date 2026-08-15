"""Conservative, deterministic cost estimates for API jobs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

from qiskit_qkd.backends import scenario_requires_aer_noise
from qiskit_qkd.config import CapabilityError, CapabilityIssue, Scenario
from qiskit_qkd.temporal import ParameterResolver

from .limits import DEFAULT_OPERATIONAL_LIMITS, OperationalLimits

AxisValue = float | int | bool | None

# Conservative upper-bound constants for the panel's compact sweep DTO. They
# intentionally over-approximate measured rows for admission safety.
COMPACT_SWEEP_ROW_BYTES = 4_096
COMPACT_SWEEP_FIXED_BYTES = 64 * 1_024
SWEEP_ARTIFACT_OVERHEAD_BYTES = 4 * 1_024


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """A deliberately conservative upper bound, not a runtime prediction."""

    estimate_kind: Literal["upper_bound"]
    evaluations: int
    pulses_per_evaluation: int
    total_pulse_events: int
    estimated_max_circuits: int
    shots_per_circuit: int
    estimated_max_shots: int
    estimated_stored_events: int
    backend: Literal["statevector", "aer", "mixed"]
    full_event_log: bool
    warnings: tuple[str, ...] = ()
    estimated_payload_bytes: int | None = None
    estimated_artifact_bytes: int | None = None
    estimated_total_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        for key in (
            "estimated_payload_bytes",
            "estimated_artifact_bytes",
            "estimated_total_bytes",
        ):
            if payload[key] is None:
                payload.pop(key)
        return payload


def require_operational_payload(
    body: Mapping[str, Any],
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> None:
    """Reject oversized known lists before constructing domain dataclasses."""

    candidate = body.get("scenario", body)
    if not isinstance(candidate, Mapping):
        return
    source = candidate.get("source")
    if isinstance(source, Mapping):
        _require_raw_list_limit(
            source.get("decoy_intensities"),
            maximum=limits.max_decoy_intensities,
            code="DECOY_INTENSITY_LIMIT_EXCEEDED",
            loc="scenario.source.decoy_intensities",
            context_key="max_decoy_intensities",
        )
    dynamic = candidate.get("dynamic")
    if isinstance(dynamic, Mapping):
        _require_raw_list_limit(
            dynamic.get("parameter_schedules"),
            maximum=limits.max_dynamic_schedules,
            code="DYNAMIC_SCHEDULE_LIMIT_EXCEEDED",
            loc="scenario.dynamic.parameter_schedules",
            context_key="max_dynamic_schedules",
        )
    protocol = candidate.get("protocol")
    if isinstance(protocol, Mapping):
        _require_raw_list_limit(
            protocol.get("basis_choices"),
            maximum=limits.max_protocol_basis_choices,
            code="PROTOCOL_BASIS_LIMIT_EXCEEDED",
            loc="scenario.protocol.basis_choices",
            context_key="max_protocol_basis_choices",
        )
    e91 = candidate.get("e91")
    if isinstance(e91, Mapping):
        for field in (
            "alice_angles_rad",
            "bob_angles_rad",
            "key_setting_pairs",
            "chsh_terms",
        ):
            _require_raw_list_limit(
                e91.get(field),
                maximum=limits.max_e91_settings,
                code="E91_SETTING_LIMIT_EXCEEDED",
                loc=f"scenario.e91.{field}",
                context_key="max_e91_settings",
            )


def estimate_run_cost(
    scenario: Scenario,
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> CostEstimate:
    """Validate and estimate one protocol execution."""

    require_operational_scenario(scenario, limits=limits)
    backend = "aer" if scenario_requires_aer_noise(scenario) else "statevector"
    return _build_estimate(
        scenario,
        pulse_counts=(scenario.pulses,),
        backend=backend,
        limits=limits,
    )


def estimate_sweep_cost(
    scenario: Scenario,
    axis: Mapping[str, Any],
    series: Mapping[str, Any] | None,
    repeats: int,
    axis_values: Sequence[AxisValue],
    series_values: Sequence[AxisValue] | None,
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> CostEstimate:
    """Validate and estimate an already-normalized sweep."""

    require_operational_scenario(scenario, limits=limits)
    pulse_counts = _sweep_pulse_counts(
        scenario,
        axis,
        series,
        repeats,
        axis_values,
        series_values,
    )
    backend = _sweep_backend(scenario, axis, series, axis_values, series_values)
    warnings: tuple[str, ...] = ()
    if len(set(pulse_counts)) > 1:
        warnings += (
            "pulses_per_evaluation is the maximum sweep point; "
            "total_pulse_events is the exact requested sum.",
        )
    if backend == "mixed":
        warnings += (
            "The sweep contains both Statevector and Aer points; the shot bound "
            "uses the more expensive Aer path.",
        )
    return _build_estimate(
        scenario,
        pulse_counts=pulse_counts,
        backend=backend,
        limits=limits,
        warnings=warnings,
        include_sweep_payload=True,
    )


def require_operational_scenario(
    scenario: Scenario,
    *,
    limits: OperationalLimits = DEFAULT_OPERATIONAL_LIMITS,
) -> None:
    """Apply non-scientific API resource limits to a valid scenario."""

    if scenario.pulses > limits.max_run_pulses:
        _raise_limit(
            code="RUN_PULSE_LIMIT_EXCEEDED",
            loc="scenario.pulses",
            value=scenario.pulses,
            maximum=limits.max_run_pulses,
            context_key="max_run_pulses",
            noun="Run pulse count",
        )
    if scenario.event_sample_size > limits.max_event_sample_size:
        _raise_limit(
            code="EVENT_SAMPLE_LIMIT_EXCEEDED",
            loc="scenario.event_sample_size",
            value=scenario.event_sample_size,
            maximum=limits.max_event_sample_size,
            context_key="max_event_sample_size",
            noun="Event sample size",
        )
    if len(scenario.source.decoy_intensities) > limits.max_decoy_intensities:
        _raise_limit(
            code="DECOY_INTENSITY_LIMIT_EXCEEDED",
            loc="scenario.source.decoy_intensities",
            value=len(scenario.source.decoy_intensities),
            maximum=limits.max_decoy_intensities,
            context_key="max_decoy_intensities",
            noun="Decoy intensity count",
        )
    if len(scenario.dynamic.parameter_schedules) > limits.max_dynamic_schedules:
        _raise_limit(
            code="DYNAMIC_SCHEDULE_LIMIT_EXCEEDED",
            loc="scenario.dynamic.parameter_schedules",
            value=len(scenario.dynamic.parameter_schedules),
            maximum=limits.max_dynamic_schedules,
            context_key="max_dynamic_schedules",
            noun="Dynamic schedule count",
        )
    if len(scenario.protocol.basis_choices) > limits.max_protocol_basis_choices:
        _raise_limit(
            code="PROTOCOL_BASIS_LIMIT_EXCEEDED",
            loc="scenario.protocol.basis_choices",
            value=len(scenario.protocol.basis_choices),
            maximum=limits.max_protocol_basis_choices,
            context_key="max_protocol_basis_choices",
            noun="Protocol basis count",
        )
    for field in (
        "alice_angles_rad",
        "bob_angles_rad",
        "key_setting_pairs",
        "chsh_terms",
    ):
        values = getattr(scenario.e91, field)
        if len(values) > limits.max_e91_settings:
            _raise_limit(
                code="E91_SETTING_LIMIT_EXCEEDED",
                loc=f"scenario.e91.{field}",
                value=len(values),
                maximum=limits.max_e91_settings,
                context_key="max_e91_settings",
                noun=f"E91 {field} count",
            )
    photon_numbers = []
    if scenario.source.mean_photon_number is not None:
        photon_numbers.append(
            ("scenario.source.mean_photon_number", scenario.source.mean_photon_number),
        )
    photon_numbers.extend(
        (
            f"scenario.source.decoy_intensities.{index}.mean_photon_number",
            intensity.mean_photon_number,
        )
        for index, intensity in enumerate(scenario.source.decoy_intensities)
    )
    for loc, mean in photon_numbers:
        if mean > limits.max_mean_photon_number:
            _raise_limit(
                code="MEAN_PHOTON_NUMBER_LIMIT_EXCEEDED",
                loc=loc,
                value=mean,
                maximum=limits.max_mean_photon_number,
                context_key="max_mean_photon_number",
                noun="Mean photon number",
            )


def _build_estimate(
    scenario: Scenario,
    *,
    pulse_counts: Sequence[int],
    backend: Literal["statevector", "aer", "mixed"],
    limits: OperationalLimits,
    warnings: tuple[str, ...] = (),
    include_sweep_payload: bool = False,
) -> CostEstimate:
    evaluations = len(pulse_counts)
    total_pulse_events = sum(pulse_counts)
    max_pulses = max(pulse_counts)
    if max_pulses > limits.max_run_pulses:
        _raise_limit(
            code="RUN_PULSE_LIMIT_EXCEEDED",
            loc="sweep.pulses",
            value=max_pulses,
            maximum=limits.max_run_pulses,
            context_key="max_run_pulses",
            noun="Maximum sweep pulse count",
        )
    if total_pulse_events > limits.max_total_pulse_events:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TOTAL_PULSE_EVENT_LIMIT_EXCEEDED",
                    loc="sweep",
                    msg=(
                        f"Request expands to {total_pulse_events} pulse events; "
                        f"the limit is {limits.max_total_pulse_events}."
                    ),
                    severity="error",
                    value=total_pulse_events,
                    context={
                        "evaluations": evaluations,
                        "max_total_pulse_events": limits.max_total_pulse_events,
                    },
                    suggestion=(
                        "Reduce pulses, axis/series points, or repeats so the "
                        f"total is at most {limits.max_total_pulse_events}."
                    ),
                ),
            ],
        )
    shots_per_circuit = (
        64
        if scenario.protocol.name == "e91" and backend in {"aer", "mixed"}
        else 1
    )
    estimated_max_shots = total_pulse_events * shots_per_circuit
    if estimated_max_shots > limits.max_estimated_quantum_shots:
        _raise_limit(
            code="QUANTUM_SHOT_LIMIT_EXCEEDED",
            loc="sweep" if evaluations > 1 else "scenario",
            value=estimated_max_shots,
            maximum=limits.max_estimated_quantum_shots,
            context_key="max_estimated_quantum_shots",
            noun="Estimated quantum shot count",
        )
    if scenario.store_full_event_log:
        estimated_stored_events = total_pulse_events
    else:
        estimated_stored_events = sum(
            min(pulses, scenario.event_sample_size) for pulses in pulse_counts
        )
    if (
        scenario.store_full_event_log
        and estimated_stored_events > limits.max_full_event_log_events
    ):
        _raise_limit(
            code="FULL_EVENT_LOG_LIMIT_EXCEEDED",
            loc="scenario.store_full_event_log",
            value=estimated_stored_events,
            maximum=limits.max_full_event_log_events,
            context_key="max_full_event_log_events",
            noun="Full event log size",
        )
    estimated_payload_bytes: int | None = None
    estimated_artifact_bytes: int | None = None
    estimated_total_bytes: int | None = None
    if include_sweep_payload:
        estimated_payload_bytes = _estimate_sweep_payload_bytes(evaluations)
        estimated_artifact_bytes = (
            estimated_payload_bytes + SWEEP_ARTIFACT_OVERHEAD_BYTES
        )
        estimated_total_bytes = estimated_payload_bytes + estimated_artifact_bytes
        if estimated_payload_bytes > limits.max_sweep_payload_bytes:
            _raise_limit(
                code="SWEEP_PAYLOAD_BYTE_LIMIT_EXCEEDED",
                loc="sweep",
                value=estimated_payload_bytes,
                maximum=limits.max_sweep_payload_bytes,
                context_key="max_sweep_payload_bytes",
                noun="Estimated sweep payload bytes",
            )
        if estimated_artifact_bytes > limits.max_sweep_artifact_bytes:
            _raise_limit(
                code="SWEEP_ARTIFACT_BYTE_LIMIT_EXCEEDED",
                loc="sweep",
                value=estimated_artifact_bytes,
                maximum=limits.max_sweep_artifact_bytes,
                context_key="max_sweep_artifact_bytes",
                noun="Estimated sweep artifact bytes",
            )
    return CostEstimate(
        estimate_kind="upper_bound",
        evaluations=evaluations,
        pulses_per_evaluation=max_pulses,
        total_pulse_events=total_pulse_events,
        estimated_max_circuits=total_pulse_events,
        shots_per_circuit=shots_per_circuit,
        estimated_max_shots=estimated_max_shots,
        estimated_stored_events=estimated_stored_events,
        backend=backend,
        full_event_log=scenario.store_full_event_log,
        warnings=warnings,
        estimated_payload_bytes=estimated_payload_bytes,
        estimated_artifact_bytes=estimated_artifact_bytes,
        estimated_total_bytes=estimated_total_bytes,
    )


def _estimate_sweep_payload_bytes(evaluations: int) -> int:
    """Return a conservative compact-DTO byte bound for ``evaluations`` rows."""

    if evaluations < 1:
        return COMPACT_SWEEP_FIXED_BYTES
    return COMPACT_SWEEP_FIXED_BYTES + evaluations * COMPACT_SWEEP_ROW_BYTES


def _sweep_pulse_counts(
    scenario: Scenario,
    axis: Mapping[str, Any],
    series: Mapping[str, Any] | None,
    repeats: int,
    axis_values: Sequence[AxisValue],
    series_values: Sequence[AxisValue] | None,
) -> tuple[int, ...]:
    axis_target = axis.get("target")
    series_target = series.get("target") if series is not None else None
    series_count = len(series_values) if series_values is not None else 1
    if axis_target == "scenario.pulses":
        point_pulses = tuple(int(value) for value in axis_values)
        return point_pulses * (series_count * repeats)
    if series_target == "scenario.pulses" and series_values is not None:
        point_pulses = tuple(int(value) for value in series_values)
        return point_pulses * (len(axis_values) * repeats)
    evaluations = len(axis_values) * series_count * repeats
    return (scenario.pulses,) * evaluations


def _sweep_backend(
    scenario: Scenario,
    axis: Mapping[str, Any],
    series: Mapping[str, Any] | None,
    axis_values: Sequence[AxisValue],
    series_values: Sequence[AxisValue] | None,
) -> Literal["statevector", "aer", "mixed"]:
    axis_target = axis.get("target")
    series_target = series.get("target") if series is not None else None
    modes: set[str] = set()
    if axis_target == "time_s" or axis.get("time_axis") is True:
        modes.update(
            "aer"
            if scenario_requires_aer_noise(
                ParameterResolver().scenario_at(scenario, time_s=float(value)),
            )
            else "statevector"
            for value in axis_values
        )
    else:
        noise_values = {
            "channel.depolarizing_probability": (
                scenario.channel.depolarizing_probability
            ),
            "channel.phase_damping_probability": (
                scenario.channel.phase_damping_probability
            ),
            "detector.readout_error_probability": (
                scenario.detector.readout_error_probability
            ),
        }
        for axis_value in axis_values:
            series_points = series_values if series_values is not None else (None,)
            for series_value in series_points:
                point_noise = dict(noise_values)
                if axis_target in point_noise:
                    point_noise[axis_target] = float(axis_value)
                if series_target in point_noise:
                    point_noise[series_target] = float(series_value)
                modes.add(
                    "aer"
                    if any(value > 0.0 for value in point_noise.values())
                    else "statevector",
                )
    if len(modes) > 1:
        return "mixed"
    return "aer" if "aer" in modes else "statevector"


def _require_raw_list_limit(
    value: Any,
    *,
    maximum: int,
    code: str,
    loc: str,
    context_key: str,
) -> None:
    if isinstance(value, list | tuple) and len(value) > maximum:
        _raise_limit(
            code=code,
            loc=loc,
            value=len(value),
            maximum=maximum,
            context_key=context_key,
            noun=f"{loc} item count",
        )


def _raise_limit(
    *,
    code: str,
    loc: str,
    value: int | float,
    maximum: int | float,
    context_key: str,
    noun: str,
) -> None:
    raise CapabilityError(
        [
            CapabilityIssue(
                code=code,
                loc=loc,
                msg=f"{noun} is {value}; the operational limit is {maximum}.",
                severity="error",
                value=value,
                context={context_key: maximum},
                suggestion=f"Reduce {loc} to at most {maximum}.",
            ),
        ],
    )
