"""Central capability registry and cross-model applicability checks."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from qiskit_qkd._json import JSONObject, JSONValue, normalize_json_value

if TYPE_CHECKING:
    from .schema import Scenario

IssueSeverity = Literal["error", "warning"]
EffectStatus = Literal["active", "ignored", "unsupported"]

PREPARE_MEASURE_SOURCE_KINDS = frozenset(
    {
        "ideal",
        "ideal_single_photon",
        "single_photon",
        "weak_coherent",
        "decoy_weak_coherent",
    },
)
ENTANGLED_SOURCE_KINDS = frozenset({"entangled_pair", "bell_pair", "e91"})
WEAK_COHERENT_SOURCE_KINDS = frozenset({"weak_coherent", "decoy_weak_coherent"})
FIBER_CHANNEL_KINDS = frozenset({"fiber"})
SPACE_CHANNEL_KINDS = frozenset({"space", "deep_space", "vacuum"})
FREE_SPACE_CHANNEL_KINDS = frozenset({"free_space", "atmospheric", "satellite"})
UNDERWATER_CHANNEL_KINDS = frozenset({"underwater", "water", "marine"})
NON_IDEAL_CHANNEL_KINDS = (
    FIBER_CHANNEL_KINDS
    | SPACE_CHANNEL_KINDS
    | FREE_SPACE_CHANNEL_KINDS
    | UNDERWATER_CHANNEL_KINDS
)
OPTICAL_GEOMETRY_CHANNEL_KINDS = (
    SPACE_CHANNEL_KINDS | FREE_SPACE_CHANNEL_KINDS | UNDERWATER_CHANNEL_KINDS
)

_DYNAMIC_TARGETS: dict[str, frozenset[str]] = {
    "source": frozenset(
        {"emission_probability", "mean_photon_number", "preparation_error_probability"},
    ),
    "channel": frozenset(
        {
            "distance_km",
            "attenuation_db_km",
            "fixed_loss_db",
            "wavelength_nm",
            "transmitter_aperture_m",
            "receiver_aperture_m",
            "beam_divergence_rad",
            "atmospheric_extinction_db_km",
            "scintillation_sigma",
            "pointing_jitter_rad",
            "underwater_extinction_m_inv",
            "underwater_scattering_broadening_ns_per_m",
            "depolarizing_probability",
            "phase_damping_probability",
            "polarization_rotation_y_rad",
            "polarization_rotation_z_rad",
            "background_count_rate_hz",
            "pmd_coefficient_ps_sqrt_km",
            "chromatic_dispersion_ps_nm_km",
            "source_spectral_width_nm",
            "polarization_dependent_loss_db",
            "classical_channel_power_mw",
            "raman_coefficient_hz_mw_km",
            "raman_filter_isolation_db",
        },
    ),
    "detector": frozenset(
        {
            "efficiency",
            "dark_count_rate_hz",
            "gate_width_s",
            "dead_time_s",
            "afterpulse_probability",
            "readout_error_probability",
        },
    ),
    "timing": frozenset(
        {"propagation_delay_s", "jitter_std_s", "clock_offset_s", "clock_drift_ppm"},
    ),
    "post_processing": frozenset(
        {"qber_abort_threshold", "qber_sample_fraction", "error_correction_efficiency"},
    ),
    "eavesdropper": frozenset(
        {
            "intercept_probability",
            "pns_split_probability",
            "pns_block_single_photon_probability",
        },
    ),
}

DYNAMIC_PARAMETER_TARGETS = frozenset(
    f"{section}.{name}" for section, names in _DYNAMIC_TARGETS.items() for name in names
)
SWEEPABLE_TARGETS = DYNAMIC_PARAMETER_TARGETS | frozenset(
    {"scenario.pulses", "scenario.clock_rate_hz"},
)


@dataclass(frozen=True, slots=True)
class CapabilityIssue:
    """Structured, JSON-safe applicability or execution issue."""

    code: str
    loc: str
    msg: str
    severity: IssueSeverity
    value: Any = None
    context: Mapping[str, Any] = field(default_factory=dict)
    suggestion: str = ""

    def to_dict(self) -> JSONObject:
        return {
            "code": self.code,
            "loc": self.loc,
            "msg": self.msg,
            "severity": self.severity,
            "value": normalize_json_value(self.value, path=f"issue.{self.code}.value"),
            "context": normalize_json_value(
                dict(self.context),
                path=f"issue.{self.code}.context",
            ),
            "suggestion": self.suggestion,
        }


class CapabilityError(ValueError):
    """Raised when a scenario or requested operation cannot affect the model."""

    def __init__(self, issues: Iterable[CapabilityIssue]) -> None:
        normalized = tuple(issues)
        if not normalized:
            raise ValueError("CapabilityError requires at least one issue")
        self.issues = normalized
        self.errors = [issue.to_dict() for issue in normalized]
        super().__init__("; ".join(issue.msg for issue in normalized))

    def __reduce__(
        self,
    ) -> tuple[type[CapabilityError], tuple[tuple[CapabilityIssue, ...]]]:
        return type(self), (self.issues,)


@dataclass(frozen=True, slots=True)
class ParameterCapability:
    target: str
    dynamic: bool = False
    sweepable: bool = False
    applicable_protocols: tuple[str, ...] = ("bb84", "e91")
    applicable_source_kinds: tuple[str, ...] = ()
    applicable_channel_kinds: tuple[str, ...] = ()
    applicable_detector_kinds: tuple[str, ...] = ()
    dependency: str | None = None
    scope: str = ""

    def to_dict(self) -> JSONObject:
        payload: JSONObject = {
            "target": self.target,
            "dynamic": self.dynamic,
            "sweepable": self.sweepable,
            "applicable_protocols": list(self.applicable_protocols),
            "scope": self.scope,
        }
        if self.applicable_source_kinds:
            payload["applicable_source_kinds"] = list(self.applicable_source_kinds)
        if self.applicable_channel_kinds:
            payload["applicable_channel_kinds"] = list(self.applicable_channel_kinds)
        if self.applicable_detector_kinds:
            payload["applicable_detector_kinds"] = list(self.applicable_detector_kinds)
        if self.dependency is not None:
            payload["dependency"] = self.dependency
        return payload


def _parameter(
    target: str,
    *,
    protocols: Iterable[str] = ("bb84", "e91"),
    source_kinds: Iterable[str] = (),
    channel_kinds: Iterable[str] = (),
    detector_kinds: Iterable[str] = (),
    dependency: str | None = None,
    scope: str = "",
) -> ParameterCapability:
    return ParameterCapability(
        target=target,
        dynamic=target in DYNAMIC_PARAMETER_TARGETS,
        sweepable=target in SWEEPABLE_TARGETS,
        applicable_protocols=tuple(protocols),
        applicable_source_kinds=tuple(source_kinds),
        applicable_channel_kinds=tuple(channel_kinds),
        applicable_detector_kinds=tuple(detector_kinds),
        dependency=dependency,
        scope=scope,
    )


def _build_parameter_capabilities() -> dict[str, ParameterCapability]:
    registry: dict[str, ParameterCapability] = {}
    for target in SWEEPABLE_TARGETS:
        registry[target] = _parameter(target)
    for target in (
        "scenario.seed",
        "scenario.event_sample_size",
        "scenario.store_full_event_log",
        "dynamic.parameter_schedules",
        "protocol.name",
        "protocol.basis_choices",
        "source.kind",
        "source.decoy_intensities",
        "channel.kind",
        "channel.pdl_axis_basis",
        "channel.pdl_axis_bit",
        "detector.kind",
        "detector.double_click_policy",
        "timing.slot_assignment_policy",
        "post_processing.sifting_enabled",
        "post_processing.reconciliation_block_size",
        "post_processing.privacy_amplification_enabled",
        "post_processing.decoy_security_estimation_enabled",
        "post_processing.decoy_security_method",
        "eavesdropper.kind",
        "e91.bell_state",
        "e91.alice_angles_rad",
        "e91.bob_angles_rad",
        "e91.key_setting_pairs",
        "e91.chsh_terms",
        "e91.bob_key_bit_flip",
        "e91.chsh_estimation_enabled",
    ):
        registry[target] = _parameter(target)

    for target in ("protocol.basis_choices", "post_processing.sifting_enabled"):
        registry[target] = _parameter(target, protocols=("bb84",))
    for target in (
        "post_processing.qber_sample_fraction",
        "post_processing.reconciliation_block_size",
        "post_processing.privacy_amplification_enabled",
        "post_processing.decoy_security_estimation_enabled",
        "post_processing.decoy_security_method",
    ):
        registry[target] = _parameter(target, protocols=("bb84",))
    for target in tuple(registry):
        if target.startswith("e91."):
            registry[target] = _parameter(target, protocols=("e91",))

    registry["source.emission_probability"] = _parameter(
        "source.emission_probability",
        source_kinds=sorted(
            (PREPARE_MEASURE_SOURCE_KINDS - WEAK_COHERENT_SOURCE_KINDS)
            | ENTANGLED_SOURCE_KINDS,
        ),
        scope="Bernoulli emission for ideal single photons or entangled pairs.",
    )
    registry["source.mean_photon_number"] = _parameter(
        "source.mean_photon_number",
        source_kinds=sorted(WEAK_COHERENT_SOURCE_KINDS),
        scope="Scalar Poisson mean; active only when decoy_intensities is empty.",
    )
    registry["source.decoy_intensities"] = _parameter(
        "source.decoy_intensities",
        source_kinds=sorted(WEAK_COHERENT_SOURCE_KINDS),
        scope=(
            "Named Poisson intensities; these take precedence over scalar "
            "mean_photon_number."
        ),
    )

    # The event-layer PDL approximation needs Alice's prepared BB84 bit/basis.
    # E91 has no such classical pre-measurement label, so advertising these
    # fields there would make sweeps look effective while the runner ignores
    # them.
    registry["channel.polarization_dependent_loss_db"] = _parameter(
        "channel.polarization_dependent_loss_db",
        protocols=("bb84",),
        scope="Classical state-dependent loss approximation for BB84 only.",
    )
    for target in ("channel.pdl_axis_basis", "channel.pdl_axis_bit"):
        registry[target] = _parameter(
            target,
            protocols=("bb84",),
            scope="Preferred axis for the BB84 event-layer PDL approximation.",
        )

    for target in tuple(registry):
        if target.startswith("eavesdropper."):
            registry[target] = _parameter(target, protocols=("bb84",))
    registry["eavesdropper.pns_split_probability"] = _parameter(
        "eavesdropper.pns_split_probability",
        protocols=("bb84",),
        source_kinds=sorted(WEAK_COHERENT_SOURCE_KINDS),
        scope="Splits multiphoton emissions from weak-coherent sources only.",
    )

    channel_groups = {
        "channel.attenuation_db_km": FIBER_CHANNEL_KINDS,
        "channel.fixed_loss_db": NON_IDEAL_CHANNEL_KINDS,
        "channel.wavelength_nm": OPTICAL_GEOMETRY_CHANNEL_KINDS,
        "channel.transmitter_aperture_m": OPTICAL_GEOMETRY_CHANNEL_KINDS,
        "channel.receiver_aperture_m": OPTICAL_GEOMETRY_CHANNEL_KINDS,
        "channel.beam_divergence_rad": OPTICAL_GEOMETRY_CHANNEL_KINDS,
        "channel.atmospheric_extinction_db_km": FREE_SPACE_CHANNEL_KINDS,
        "channel.scintillation_sigma": FREE_SPACE_CHANNEL_KINDS
        | UNDERWATER_CHANNEL_KINDS,
        "channel.pointing_jitter_rad": FREE_SPACE_CHANNEL_KINDS
        | UNDERWATER_CHANNEL_KINDS,
        "channel.underwater_extinction_m_inv": UNDERWATER_CHANNEL_KINDS,
        "channel.underwater_scattering_broadening_ns_per_m": UNDERWATER_CHANNEL_KINDS,
        "channel.pmd_coefficient_ps_sqrt_km": FIBER_CHANNEL_KINDS,
        "channel.chromatic_dispersion_ps_nm_km": FIBER_CHANNEL_KINDS,
        "channel.source_spectral_width_nm": FIBER_CHANNEL_KINDS,
        "channel.classical_channel_power_mw": FIBER_CHANNEL_KINDS,
        "channel.raman_coefficient_hz_mw_km": FIBER_CHANNEL_KINDS,
        "channel.raman_filter_isolation_db": FIBER_CHANNEL_KINDS,
    }
    for target, kinds in channel_groups.items():
        registry[target] = _parameter(target, channel_kinds=sorted(kinds))
    for target in (
        "channel.depolarizing_probability",
        "channel.phase_damping_probability",
        "detector.readout_error_probability",
    ):
        existing = registry[target]
        registry[target] = ParameterCapability(
            target=existing.target,
            dynamic=existing.dynamic,
            sweepable=existing.sweepable,
            applicable_protocols=existing.applicable_protocols,
            applicable_source_kinds=existing.applicable_source_kinds,
            applicable_channel_kinds=existing.applicable_channel_kinds,
            applicable_detector_kinds=existing.applicable_detector_kinds,
            dependency="qiskit-aer",
            scope="Qiskit Aer noise model.",
        )
    return dict(sorted(registry.items()))


PARAMETER_CAPABILITIES = _build_parameter_capabilities()

_COMMON_METRICS = (
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
    "timing_discards",
    "dead_time_discards",
    "afterpulse_clicks",
)

METRIC_CAPABILITIES: dict[str, JSONObject] = {
    key: {
        "key": key,
        "applicable_protocols": ["bb84", "e91"],
        "defined_when": "always",
        "scope": "Aggregate simulation metric.",
    }
    for key in _COMMON_METRICS
}
METRIC_CAPABILITIES["qber"] = {
    "key": "qber",
    "applicable_protocols": ["bb84", "e91"],
    "defined_when": "sifted > 0",
    "scope": "Observed error fraction; qber_defined must be checked.",
}
METRIC_CAPABILITIES["abort"] = {
    "key": "abort",
    "applicable_protocols": ["bb84", "e91"],
    "defined_when": "always",
    "scope": "legacy aggregate threshold flag; not security/key/verification",
}
METRIC_CAPABILITIES["secret_key_rate_bps"] = {
    "key": "secret_key_rate_bps",
    "applicable_protocols": ["bb84", "e91"],
    "defined_when": "model assessment permits an estimate",
    "scope": "Estimated pedagogical/asymptotic key rate, not a security proof.",
}
for key in ("eve_intercepted_fraction", "eve_information_estimate"):
    METRIC_CAPABILITIES[key] = {
        "key": key,
        "applicable_protocols": ["bb84"],
        "defined_when": "BB84 eavesdropper model is active",
        "scope": "Pedagogical adversary diagnostic.",
    }
METRIC_CAPABILITIES["chsh_s"] = {
    "key": "chsh_s",
    "applicable_protocols": ["e91"],
    "defined_when": (
        "CHSH estimation is enabled and every required setting has coincidences"
    ),
    "scope": "Observed CHSH estimator without a statistical significance claim.",
}
METRIC_CAPABILITIES["qber_margin"] = {
    "key": "qber_margin",
    "applicable_protocols": ["bb84", "e91"],
    "defined_when": "qber_defined and qber_abort_threshold is configured",
    "scope": "Diagnostic distance from the configured abort threshold.",
}
METRIC_CAPABILITIES["chsh_margin"] = {
    "key": "chsh_margin",
    "applicable_protocols": ["e91"],
    "defined_when": "chsh_s is defined",
    "scope": "Observed distance from S=2; no significance test is implied.",
}


def capability_issues(scenario: Scenario) -> tuple[CapabilityIssue, ...]:
    """Return hard compatibility errors and ignored-parameter warnings."""

    issues: list[CapabilityIssue] = []
    protocol = scenario.protocol.name
    source_kind = scenario.source.kind
    if protocol == "bb84" and source_kind in ENTANGLED_SOURCE_KINDS:
        issues.append(
            CapabilityIssue(
                code="BB84_SOURCE_INCOMPATIBLE",
                loc="source.kind",
                msg=f"BB84 cannot execute with entangled source kind {source_kind!r}.",
                severity="error",
                value=source_kind,
                context={"protocol": protocol},
                suggestion=(
                    "Use an ideal/weak-coherent source, or change protocol.name "
                    "to 'e91'."
                ),
            ),
        )
    if protocol == "e91" and source_kind not in ENTANGLED_SOURCE_KINDS:
        issues.append(
            CapabilityIssue(
                code="E91_SOURCE_REQUIRED",
                loc="source.kind",
                msg=f"E91 requires an entangled-pair source, got {source_kind!r}.",
                severity="error",
                value=source_kind,
                context={"protocol": protocol},
                suggestion=(
                    "Set source.kind to 'entangled_pair' (or 'bell_pair'/'e91')."
                ),
            ),
        )
    if protocol == "e91" and scenario.eavesdropper.kind != "none":
        issues.append(
            CapabilityIssue(
                code="E91_EAVESDROPPER_UNSUPPORTED",
                loc="eavesdropper.kind",
                msg=(
                    "E91 has no executable eavesdropper model for "
                    f"{scenario.eavesdropper.kind!r}."
                ),
                severity="error",
                value=scenario.eavesdropper.kind,
                context={"protocol": protocol},
                suggestion="Set eavesdropper.kind to 'none', or use BB84.",
            ),
        )

    if (
        scenario.source.decoy_intensities
        and scenario.source.mean_photon_number is not None
    ):
        issues.append(
            CapabilityIssue(
                code="SOURCE_MEAN_PHOTON_NUMBER_SHADOWED",
                loc="source.mean_photon_number",
                msg=(
                    "mean_photon_number is ignored because decoy_intensities "
                    "is non-empty."
                ),
                severity="warning",
                value=scenario.source.mean_photon_number,
                context={"source_kind": source_kind},
                suggestion=(
                    "Clear decoy_intensities for a scalar weak-coherent source, "
                    "or vary a "
                    "named decoy intensity explicitly."
                ),
            ),
        )

    issues.extend(_ignored_parameter_issues(scenario))
    return tuple(issues)


def require_executable_scenario(scenario: Scenario) -> None:
    """Reject cross-model combinations that a protocol runner cannot execute."""

    errors = [
        issue for issue in capability_issues(scenario) if issue.severity == "error"
    ]
    if errors:
        raise CapabilityError(errors)


def require_effective_target(
    scenario: Scenario,
    target: str,
    purpose: str = "sweep",
) -> str:
    """Return a normalized target only when it affects the active model."""

    require_executable_scenario(scenario)
    from .dynamics import validate_parameter_target

    try:
        normalized = validate_parameter_target(target)
    except (TypeError, ValueError) as exc:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TARGET_NOT_SUPPORTED",
                    loc=f"{purpose}.target",
                    msg=f"{purpose} target {target!r} is not registered.",
                    severity="error",
                    value=target,
                    context={"purpose": purpose},
                    suggestion=(
                        "Choose a target advertised as sweepable by /api/catalog."
                    ),
                ),
            ],
        ) from exc

    status, reason = _target_effect(scenario, normalized)
    if status != "active":
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TARGET_HAS_NO_EFFECT",
                    loc=normalized,
                    msg=f"{purpose} target {normalized!r} has no effect: {reason}",
                    severity="error",
                    value=_parameter_value(scenario, normalized),
                    context={
                        "purpose": purpose,
                        "effect_status": status,
                        "protocol": scenario.protocol.name,
                        "source_kind": scenario.source.kind,
                        "channel_kind": scenario.channel.kind,
                        "detector_kind": scenario.detector.kind,
                    },
                    suggestion=_target_suggestion(normalized, scenario),
                ),
            ],
        )
    return normalized


def require_time_evolution(
    scenario: Scenario,
    time_points_s: Iterable[float],
) -> None:
    """Require a supported, non-constant schedule over the requested points."""

    require_executable_scenario(scenario)
    raw_points = tuple(time_points_s)
    if any(
        isinstance(point, bool) or not isinstance(point, int | float)
        for point in raw_points
    ):
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TIME_POINTS_INVALID",
                    loc="axis.values",
                    msg="time_s points must be numeric, finite, and non-negative.",
                    severity="error",
                    value=list(raw_points),
                    context={},
                    suggestion="Replace non-numeric time values with seconds.",
                ),
            ],
        )
    try:
        points = tuple(float(point) for point in raw_points)
    except (TypeError, ValueError) as exc:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TIME_POINTS_INVALID",
                    loc="axis.values",
                    msg="time_s points must be numeric, finite, and non-negative.",
                    severity="error",
                    value=list(raw_points),
                    context={},
                    suggestion="Replace non-numeric time values with seconds.",
                ),
            ],
        ) from exc
    if scenario.protocol.name != "bb84":
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TIME_SWEEP_UNSUPPORTED_PROTOCOL",
                    loc="axis.target",
                    msg=(
                        "time_s sweeps are not implemented for "
                        f"{scenario.protocol.name!r}."
                    ),
                    severity="error",
                    value="time_s",
                    context={"protocol": scenario.protocol.name},
                    suggestion="Use BB84, or sweep a static E91 parameter instead.",
                ),
            ],
        )
    if len(points) < 2:
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TIME_EVOLUTION_REQUIRED",
                    loc="axis.values",
                    msg="A time sweep requires at least two distinct requested times.",
                    severity="error",
                    value=list(points),
                    context={"time_points": len(points)},
                    suggestion=(
                        "Provide at least two times covered by a varying schedule."
                    ),
                ),
            ],
        )
    if any(not math.isfinite(point) or point < 0.0 for point in points):
        raise CapabilityError(
            [
                CapabilityIssue(
                    code="TIME_POINTS_INVALID",
                    loc="axis.values",
                    msg="time_s points must be finite and non-negative.",
                    severity="error",
                    value=list(points),
                    context={},
                    suggestion="Remove negative, NaN, or infinite time values.",
                ),
            ],
        )

    from qiskit_qkd.temporal import ParameterResolver

    resolver = ParameterResolver()
    for schedule in scenario.dynamic.parameter_schedules:
        profile = schedule.profile.to_dict()
        if profile.get("kind") == "constant":
            continue
        try:
            effective_scenarios = tuple(
                resolver.scenario_at(scenario, time_s=point) for point in points
            )
            values = tuple(
                _parameter_value(effective, schedule.target)
                for effective in effective_scenarios
            )
        except (TypeError, ValueError) as exc:
            raise CapabilityError(
                [
                    CapabilityIssue(
                        code="TIME_RESOLUTION_FAILED",
                        loc="dynamic.parameter_schedules",
                        msg=f"Cannot resolve time evolution: {exc}",
                        severity="error",
                        value=schedule.target,
                        context={"time_points_s": list(points)},
                        suggestion=(
                            "Fix overlapping schedules or invalid scheduled values."
                        ),
                    ),
                ],
            ) from exc
        if len(set(values)) > 1 and any(
            _target_effect(effective, schedule.target)[0] == "active"
            for effective in effective_scenarios
        ):
            return

    raise CapabilityError(
        [
            CapabilityIssue(
                code="TIME_EVOLUTION_REQUIRED",
                loc="dynamic.parameter_schedules",
                msg=(
                    "time_s has no non-constant effective schedule over the "
                    "requested points."
                ),
                severity="error",
                value=list(points),
                context={"schedule_count": len(scenario.dynamic.parameter_schedules)},
                suggestion=(
                    "Add a linear or exponential schedule whose effective values "
                    "change "
                    "across the requested time range."
                ),
            ),
        ],
    )


def effective_parameter_snapshot(scenario: Scenario) -> JSONObject:
    """Describe the concrete models, effective targets, and metric scope."""

    consumed: list[JSONValue] = []
    ignored: list[JSONValue] = []
    effective_values: JSONObject = {}
    ignored_values: JSONObject = {}
    for target in PARAMETER_CAPABILITIES:
        status, _reason = _target_effect(scenario, target)
        value = _json_safe_parameter_value(
            _parameter_value(scenario, target),
            path=f"effective_model.{target}",
        )
        if status == "active":
            consumed.append(target)
            effective_values[target] = value
        else:
            ignored.append(target)
            ignored_values[target] = value
    warnings = [
        issue.to_dict()
        for issue in capability_issues(scenario)
        if issue.severity == "warning"
    ]
    return {
        "protocol_name": scenario.protocol.name,
        "protocol_model": "E91Protocol"
        if scenario.protocol.name == "e91"
        else "BB84Protocol",
        "source_kind": scenario.source.kind,
        "source_model": _source_model(scenario.source.kind),
        "channel_kind": scenario.channel.kind,
        "channel_model": _channel_model(scenario.channel.kind),
        "detector_kind": scenario.detector.kind,
        "detector_model": "ThresholdDetector",
        "consumed_parameters": consumed,
        "ignored_parameters": ignored,
        "effective_values": effective_values,
        "ignored_values": ignored_values,
        "derived_parameters": _derived_parameter_snapshot(scenario),
        "applicable_metrics": [
            key
            for key, metadata in METRIC_CAPABILITIES.items()
            if scenario.protocol.name in metadata["applicable_protocols"]
        ],
        "capability_warnings": warnings,
    }


def _derived_parameter_snapshot(scenario: Scenario) -> JSONObject:
    from qiskit_qkd.channels import (
        channel_from_config,
        effective_background_count_rate_hz,
        effective_jitter_std_s,
        raman_count_rate_hz,
        temporal_broadening_s,
    )

    channel = channel_from_config(scenario.channel)
    return {
        "effective_background_count_rate_hz": effective_background_count_rate_hz(
            scenario.channel,
        ),
        "effective_jitter_std_s": effective_jitter_std_s(scenario),
        "temporal_broadening_s": temporal_broadening_s(scenario.channel),
        "raman_count_rate_hz": raman_count_rate_hz(scenario.channel),
        "channel_transmittance": channel.transmittance(),
        "channel_loss_db": channel.loss_db,
    }


def capability_registry_payload() -> JSONObject:
    """Return the JSON-safe registry exposed by the panel API."""

    return {
        "parameters": {
            target: capability.to_dict()
            for target, capability in PARAMETER_CAPABILITIES.items()
        },
        "metrics": dict(METRIC_CAPABILITIES),
        "aliases": {
            "source": {
                "prepare_measure": sorted(PREPARE_MEASURE_SOURCE_KINDS),
                "weak_coherent": sorted(WEAK_COHERENT_SOURCE_KINDS),
                "entangled_pair": sorted(ENTANGLED_SOURCE_KINDS),
            },
            "channel": {
                "fiber": sorted(FIBER_CHANNEL_KINDS),
                "space": sorted(SPACE_CHANNEL_KINDS),
                "free_space": sorted(FREE_SPACE_CHANNEL_KINDS),
                "underwater": sorted(UNDERWATER_CHANNEL_KINDS),
            },
            "detector": {"threshold": ["ideal", "threshold"]},
        },
    }


def parameter_capability_payload(target: str) -> JSONObject:
    capability = PARAMETER_CAPABILITIES.get(target)
    return {} if capability is None else capability.to_dict()


def metric_capability_payload(key: str) -> JSONObject:
    return dict(METRIC_CAPABILITIES.get(key, {}))


def _ignored_parameter_issues(scenario: Scenario) -> list[CapabilityIssue]:
    from .schema import (
        ChannelConfig,
        DetectorConfig,
        E91Config,
        EveConfig,
        PostProcessingConfig,
        ProtocolConfig,
        SourceConfig,
        TimingConfig,
    )

    defaults: dict[str, Any] = {}
    for section_name, config in (
        ("protocol", ProtocolConfig()),
        ("source", SourceConfig()),
        ("channel", ChannelConfig()),
        ("detector", DetectorConfig()),
        ("timing", TimingConfig()),
        ("post_processing", PostProcessingConfig()),
        ("eavesdropper", EveConfig()),
        ("e91", E91Config()),
    ):
        for name, value in config.to_dict().items():
            defaults[f"{section_name}.{name}"] = value

    issues: list[CapabilityIssue] = []
    for target, default in defaults.items():
        if target in {
            "protocol.name",
            "source.kind",
            "source.mean_photon_number",
            "channel.kind",
            "detector.kind",
            "eavesdropper.kind",
        }:
            continue
        value = _parameter_value(scenario, target)
        json_value = _json_safe_parameter_value(
            value,
            path=f"capability_defaults.{target}.configured",
        )
        json_default = _json_safe_parameter_value(
            default,
            path=f"capability_defaults.{target}.default",
        )
        if json_value == json_default:
            continue
        status, reason = _target_effect(scenario, target)
        if status == "active":
            continue
        if _is_neutral_ignored_value(json_value):
            continue
        section = target.split(".", 1)[0]
        issues.append(
            CapabilityIssue(
                code=f"{section.upper()}_PARAMETER_IGNORED",
                loc=target,
                msg=f"{target} is configured but has no supported effect: {reason}",
                severity="warning",
                value=value,
                context={
                    "effect_status": status,
                    "protocol": scenario.protocol.name,
                    "source_kind": scenario.source.kind,
                    "channel_kind": scenario.channel.kind,
                },
                suggestion=_target_suggestion(target, scenario),
            ),
        )
    return issues


def _is_neutral_ignored_value(value: JSONValue) -> bool:
    """Return whether an inapplicable value is only a structural placeholder."""

    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return value == 0
    if isinstance(value, list):
        return not value
    return False


def _target_effect(scenario: Scenario, target: str) -> tuple[EffectStatus, str]:
    capability = PARAMETER_CAPABILITIES.get(target)
    if capability is None:
        return "unsupported", "the parameter is not registered"
    if scenario.protocol.name not in capability.applicable_protocols:
        return "ignored", f"it is not consumed by protocol {scenario.protocol.name!r}"
    if capability.applicable_source_kinds and (
        scenario.source.kind not in capability.applicable_source_kinds
    ):
        return "ignored", f"it is not consumed by source kind {scenario.source.kind!r}"
    if capability.applicable_channel_kinds and (
        scenario.channel.kind not in capability.applicable_channel_kinds
    ):
        return (
            "ignored",
            f"it is not supported by channel kind {scenario.channel.kind!r}",
        )
    if capability.applicable_detector_kinds and (
        scenario.detector.kind not in capability.applicable_detector_kinds
    ):
        return (
            "ignored",
            f"it is not consumed by detector kind {scenario.detector.kind!r}",
        )
    no_effect_reason = _conditional_no_effect_reason(scenario, target)
    if no_effect_reason is not None:
        return "ignored", no_effect_reason
    if target == "source.mean_photon_number" and scenario.source.decoy_intensities:
        return "ignored", "decoy_intensities takes precedence over the scalar mean"
    if target.startswith("eavesdropper.") and target != "eavesdropper.kind":
        if scenario.eavesdropper.kind == "none":
            return "ignored", "no eavesdropper model is active"
        if target == "eavesdropper.intercept_probability" and (
            scenario.eavesdropper.kind != "intercept_resend"
        ):
            return "ignored", "intercept_probability belongs to intercept_resend"
        if target.startswith("eavesdropper.pns_") and (
            scenario.eavesdropper.kind != "photon_number_splitting"
        ):
            return "ignored", "PNS parameters require photon_number_splitting"
    return "active", "the active model consumes this parameter"


def _conditional_no_effect_reason(scenario: Scenario, target: str) -> str | None:
    channel = scenario.channel
    if (
        scenario.protocol.name == "bb84"
        and "X" not in scenario.protocol.basis_choices
        and target
        in {
            "channel.phase_damping_probability",
            "channel.polarization_rotation_z_rad",
        }
    ):
        return "phase-only channel effects are unobservable without the BB84 X basis"
    if target == "channel.distance_km":
        if channel.kind in OPTICAL_GEOMETRY_CHANNEL_KINDS:
            return None
        if channel.kind in FIBER_CHANNEL_KINDS and channel.attenuation_db_km > 0.0:
            return None
        if any(
            (
                channel.pmd_coefficient_ps_sqrt_km > 0.0,
                channel.underwater_scattering_broadening_ns_per_m > 0.0,
                channel.chromatic_dispersion_ps_nm_km != 0.0
                and channel.source_spectral_width_nm > 0.0,
                channel.classical_channel_power_mw > 0.0
                and channel.raman_coefficient_hz_mw_km > 0.0,
            ),
        ):
            return None
        return "distance is disconnected from every active loss/impairment model"
    if (
        target
        in {
            "channel.attenuation_db_km",
            "channel.atmospheric_extinction_db_km",
            "channel.pointing_jitter_rad",
            "channel.underwater_extinction_m_inv",
            "channel.underwater_scattering_broadening_ns_per_m",
            "channel.pmd_coefficient_ps_sqrt_km",
            "channel.beam_divergence_rad",
        }
        and channel.distance_km == 0.0
    ):
        return "the configured propagation distance is zero"
    if target == "channel.wavelength_nm" and (
        channel.distance_km == 0.0 or channel.beam_divergence_rad > 0.0
    ):
        return (
            "wavelength affects diffraction only at nonzero distance without "
            "explicit divergence"
        )
    if target == "channel.chromatic_dispersion_ps_nm_km" and (
        channel.distance_km == 0.0 or channel.source_spectral_width_nm == 0.0
    ):
        return (
            "chromatic broadening requires nonzero distance and source spectral width"
        )
    if target == "channel.source_spectral_width_nm" and (
        channel.distance_km == 0.0 or channel.chromatic_dispersion_ps_nm_km == 0.0
    ):
        return "spectral-width broadening requires nonzero distance and dispersion"
    if target in {"channel.pdl_axis_basis", "channel.pdl_axis_bit"} and (
        channel.polarization_dependent_loss_db == 0.0
    ):
        return "the PDL axis has no effect while polarization-dependent loss is zero"
    if target == "channel.classical_channel_power_mw" and (
        channel.distance_km == 0.0 or channel.raman_coefficient_hz_mw_km == 0.0
    ):
        return "Raman background requires nonzero distance and Raman coefficient"
    if target == "channel.raman_coefficient_hz_mw_km" and (
        channel.distance_km == 0.0 or channel.classical_channel_power_mw == 0.0
    ):
        return "Raman background requires nonzero distance and classical power"
    if target == "channel.raman_filter_isolation_db" and (
        channel.distance_km == 0.0
        or channel.classical_channel_power_mw == 0.0
        or channel.raman_coefficient_hz_mw_km == 0.0
    ):
        return "filter isolation has no effect without a nonzero Raman background"
    return None


def _target_suggestion(target: str, scenario: Scenario) -> str:
    if target == "source.mean_photon_number" and scenario.source.decoy_intensities:
        return (
            "Clear source.decoy_intensities for a scalar source, or add a named-decoy "
            "intensity target."
        )
    if target == "channel.pointing_jitter_rad" and (
        scenario.channel.kind in SPACE_CHANNEL_KINDS
    ):
        return (
            "Use channel.kind 'free_space'/'satellite', or implement pointing "
            "in SpaceChannel."
        )
    capability = PARAMETER_CAPABILITIES.get(target)
    if capability is not None and capability.applicable_channel_kinds:
        return "Use one of the supported channel kinds: " + ", ".join(
            capability.applicable_channel_kinds,
        )
    if capability is not None and capability.applicable_source_kinds:
        return "Use one of the supported source kinds: " + ", ".join(
            capability.applicable_source_kinds,
        )
    return "Choose a target whose applicability metadata matches the active scenario."


def _parameter_value(scenario: Scenario, target: str) -> Any:
    section, name = target.split(".", 1)
    if section == "scenario":
        return getattr(scenario, name)
    return getattr(getattr(scenario, section), name)


def _json_safe_parameter_value(value: Any, *, path: str) -> JSONValue:
    if isinstance(value, Mapping):
        prepared = {
            str(key): _json_safe_parameter_value(item, path=f"{path}.{key}")
            for key, item in value.items()
        }
        return normalize_json_value(prepared, path=path)
    if isinstance(value, list | tuple):
        prepared_items = [
            _json_safe_parameter_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
        return normalize_json_value(prepared_items, path=path)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_safe_parameter_value(to_dict(), path=path)
    return normalize_json_value(value, path=path)


def _source_model(kind: str) -> str:
    if kind in WEAK_COHERENT_SOURCE_KINDS:
        return "WeakCoherentDecoySource"
    if kind in ENTANGLED_SOURCE_KINDS:
        return "EntangledPairSource"
    return "IdealSinglePhotonSource"


def _channel_model(kind: str) -> str:
    if kind in FIBER_CHANNEL_KINDS:
        return "FiberChannel"
    if kind in FREE_SPACE_CHANNEL_KINDS:
        return "FreeSpaceChannel"
    if kind in UNDERWATER_CHANNEL_KINDS:
        return "UnderwaterChannel"
    if kind in SPACE_CHANNEL_KINDS:
        return "SpaceChannel"
    return "IdealChannel"


__all__ = [
    "CapabilityError",
    "CapabilityIssue",
    "DYNAMIC_PARAMETER_TARGETS",
    "METRIC_CAPABILITIES",
    "PARAMETER_CAPABILITIES",
    "SWEEPABLE_TARGETS",
    "capability_issues",
    "capability_registry_payload",
    "effective_parameter_snapshot",
    "metric_capability_payload",
    "parameter_capability_payload",
    "require_effective_target",
    "require_executable_scenario",
    "require_time_evolution",
]
