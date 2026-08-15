"""Explicit, scientifically scoped interpretation of simulation results."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Self

from qiskit_qkd._json import JSONObject, normalize_json_object
from qiskit_qkd._validation import (
    reject_unknown_fields,
    require_bool,
    require_choice,
    require_non_empty_str,
    require_non_negative_int,
    require_non_negative_number,
    require_optional_probability,
)
from qiskit_qkd.config import Scenario

from .metrics import Metrics

DATA_STATUSES = {"available", "insufficient_data"}
QBER_METHODS = {
    "revealed_sample",
    "full_sifted_key_diagnostic",
    "unavailable",
}
DECISION_SOURCES = {
    "classical_estimate",
    "metrics_legacy",
    "disabled",
    "unavailable",
}
VERIFICATION_STATUSES = {
    "passed",
    "failed",
    "not_performed",
    "not_applicable",
    "unknown",
}
KEY_STATUSES = {
    "estimated_key_available",
    "no_key_insufficient_data",
    "no_key_threshold_exceeded",
    "no_key_verification_failed",
    "no_extractable_key",
    "unknown",
}
RATE_STATUSES = {
    "available",
    "unavailable",
    "inconsistent_with_key_status",
}
SECURITY_SCOPE = "pedagogical_asymptotic_diagnostic"
E91_CONCLUSION_SCOPE = "diagnostic_fair_sampling_no_significance_test"
CHSH_CLASSICAL_BOUND = 2.0
REASON_MESSAGES = {
    "NO_SIFTED_BITS": "No sifted bits were observed.",
    "QBER_UNDEFINED": "QBER is undefined because its denominator is zero.",
    "QBER_THRESHOLD_EXCEEDED": (
        "The observed QBER estimate exceeds the configured threshold."
    ),
    "CLASSICAL_QBER_EVIDENCE_MISMATCH": (
        "The stored classical QBER fields disagree with aggregate error evidence."
    ),
    "METRICS_CLASSICAL_ABORT_MISMATCH": (
        "The legacy aggregate abort flag disagrees with the classical decision."
    ),
    "CLASSICAL_THRESHOLD_EVIDENCE_MISMATCH": (
        "The stored classical threshold decision disagrees with the observed QBER."
    ),
    "METRICS_THRESHOLD_EVIDENCE_MISMATCH": (
        "The legacy aggregate threshold decision disagrees with the observed QBER."
    ),
    "CLASSICAL_THRESHOLD_CONFIG_MISMATCH": (
        "The stored classical threshold disagrees with the serialized scenario."
    ),
    "VERIFICATION_FAILED": "Classical key verification found residual mismatches.",
    "NO_EXTRACTABLE_KEY": "No extractable key was produced by the modeled processing.",
    "LEGACY_RATE_INCONSISTENT_WITH_KEY_STATUS": (
        "The legacy asymptotic rate is positive although the assessed key is "
        "unavailable."
    ),
    "CHSH_UNAVAILABLE": "No observed CHSH value is supported by coincidence samples.",
    "CHSH_DISABLED": "CHSH estimation was disabled for this scenario.",
    "BELL_CHSH_EVIDENCE_MISMATCH": (
        "The stored Bell summary disagrees with CHSH recomputed from setting counts."
    ),
    "METRICS_CHSH_EVIDENCE_MISMATCH": (
        "The aggregate CHSH value disagrees with CHSH recomputed from setting counts."
    ),
}


@dataclass(frozen=True, slots=True)
class ResultAssessment:
    """Evidence-aware assessment serialized by result schema v2.

    This object does not constitute a finite-key or composable security claim.
    It records which observations and diagnostic assumptions support each
    result-level decision while legacy scalar metrics remain serializable.
    """

    protocol: str
    data_status: str
    qber_defined: bool
    qber_value: float | None
    sample_size: int
    qber_method: str
    threshold: float | None
    threshold_exceeded: bool | None
    threshold_decision_source: str
    verification_status: str
    key_status: str
    rate_estimate_status: str
    rate_estimate_bps: float | None
    rate_estimate_method: str
    security_scope: str = SECURITY_SCOPE
    finite_key: bool = False
    composable: bool = False
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    observed_chsh_s: float | None = None
    chsh_sample_size: int = 0
    chsh_sample_size_by_term: dict[str, int] = field(default_factory=dict)
    observed_threshold_exceeded: bool | None = None
    conclusion_scope: str | None = None

    def __getattribute__(self, name: str) -> Any:
        value = object.__getattribute__(self, name)
        if name == "chsh_sample_size_by_term":
            return dict(value)
        return value

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "protocol",
            require_non_empty_str("protocol", self.protocol).lower(),
        )
        object.__setattr__(
            self,
            "data_status",
            require_choice("data_status", self.data_status, DATA_STATUSES),
        )
        object.__setattr__(
            self,
            "qber_defined",
            require_bool("qber_defined", self.qber_defined),
        )
        object.__setattr__(
            self,
            "qber_value",
            require_optional_probability("qber_value", self.qber_value),
        )
        object.__setattr__(
            self,
            "sample_size",
            require_non_negative_int("sample_size", self.sample_size),
        )
        object.__setattr__(
            self,
            "qber_method",
            require_choice("qber_method", self.qber_method, QBER_METHODS),
        )
        object.__setattr__(
            self,
            "threshold",
            require_optional_probability("threshold", self.threshold),
        )
        if self.threshold_exceeded is not None:
            object.__setattr__(
                self,
                "threshold_exceeded",
                require_bool("threshold_exceeded", self.threshold_exceeded),
            )
        object.__setattr__(
            self,
            "threshold_decision_source",
            require_choice(
                "threshold_decision_source",
                self.threshold_decision_source,
                DECISION_SOURCES,
            ),
        )
        object.__setattr__(
            self,
            "verification_status",
            require_choice(
                "verification_status",
                self.verification_status,
                VERIFICATION_STATUSES,
            ),
        )
        object.__setattr__(
            self,
            "key_status",
            require_choice("key_status", self.key_status, KEY_STATUSES),
        )
        object.__setattr__(
            self,
            "rate_estimate_status",
            require_choice(
                "rate_estimate_status",
                self.rate_estimate_status,
                RATE_STATUSES,
            ),
        )
        if self.rate_estimate_bps is not None:
            object.__setattr__(
                self,
                "rate_estimate_bps",
                require_non_negative_number(
                    "rate_estimate_bps",
                    self.rate_estimate_bps,
                ),
            )
        object.__setattr__(
            self,
            "rate_estimate_method",
            require_non_empty_str("rate_estimate_method", self.rate_estimate_method),
        )
        object.__setattr__(
            self,
            "security_scope",
            require_choice("security_scope", self.security_scope, {SECURITY_SCOPE}),
        )
        object.__setattr__(
            self,
            "finite_key",
            require_bool("finite_key", self.finite_key),
        )
        object.__setattr__(
            self,
            "composable",
            require_bool("composable", self.composable),
        )
        if self.finite_key or self.composable:
            raise ValueError(
                "ResultAssessment is pedagogical/asymptotic; finite_key and "
                "composable must remain false",
            )
        object.__setattr__(
            self,
            "reason_codes",
            _normalized_strings("reason_codes", self.reason_codes),
        )
        object.__setattr__(
            self,
            "reasons",
            _normalized_strings("reasons", self.reasons),
        )
        object.__setattr__(
            self,
            "assumptions",
            _normalized_strings("assumptions", self.assumptions),
        )
        if self.observed_chsh_s is not None:
            chsh_s = require_non_negative_number(
                "observed_chsh_s",
                self.observed_chsh_s,
            )
            if chsh_s > 4.0:
                raise ValueError("observed_chsh_s must not exceed 4")
            object.__setattr__(self, "observed_chsh_s", chsh_s)
        object.__setattr__(
            self,
            "chsh_sample_size",
            require_non_negative_int("chsh_sample_size", self.chsh_sample_size),
        )
        if not isinstance(self.chsh_sample_size_by_term, Mapping):
            raise TypeError("chsh_sample_size_by_term must be a mapping")
        sample_sizes = {
            require_non_empty_str("chsh_sample_size_by_term key", key): (
                require_non_negative_int(
                    f"chsh_sample_size_by_term[{key!r}]",
                    value,
                )
            )
            for key, value in self.chsh_sample_size_by_term.items()
        }
        object.__setattr__(self, "chsh_sample_size_by_term", sample_sizes)
        if self.observed_threshold_exceeded is not None:
            object.__setattr__(
                self,
                "observed_threshold_exceeded",
                require_bool(
                    "observed_threshold_exceeded",
                    self.observed_threshold_exceeded,
                ),
            )
        if self.conclusion_scope is not None:
            object.__setattr__(
                self,
                "conclusion_scope",
                require_choice(
                    "conclusion_scope",
                    self.conclusion_scope,
                    {E91_CONCLUSION_SCOPE},
                ),
            )
        if self.qber_defined != (self.qber_value is not None):
            raise ValueError("qber_defined must match whether qber_value is present")
        if self.qber_defined and (
            self.sample_size == 0 or self.qber_method == "unavailable"
        ):
            raise ValueError(
                "a defined QBER requires a positive sample_size and an evidence method",
            )
        if not self.qber_defined and (
            self.sample_size != 0 or self.qber_method != "unavailable"
        ):
            raise ValueError(
                "an undefined QBER must use sample_size=0 and "
                "qber_method='unavailable'",
            )
        if self.threshold_exceeded is not None and not self.qber_defined:
            raise ValueError("threshold_exceeded requires a defined QBER")
        if self.data_status == "insufficient_data" and self.qber_defined:
            raise ValueError("data_status cannot be insufficient when QBER is defined")
        if self.data_status == "available" and not self.qber_defined:
            raise ValueError("data_status cannot be available when QBER is undefined")
        if self.threshold is None:
            if self.threshold_decision_source != "disabled":
                raise ValueError(
                    "a disabled threshold must use "
                    "threshold_decision_source='disabled'",
                )
            if self.threshold_exceeded is not None:
                raise ValueError("a disabled threshold has no exceeded decision")
        elif not self.qber_defined:
            if self.threshold_decision_source != "unavailable":
                raise ValueError(
                    "undefined QBER requires an unavailable threshold decision",
                )
        elif self.threshold_decision_source not in {
            "classical_estimate",
            "metrics_legacy",
        }:
            raise ValueError(
                "a QBER threshold decision requires an observed decision source",
            )
        if (
            self.threshold is not None
            and self.qber_value is not None
            and self.threshold_exceeded != (self.qber_value > self.threshold)
        ):
            raise ValueError(
                "threshold_exceeded must represent qber_value > threshold",
            )
        if not self.qber_defined and self.key_status != "no_key_insufficient_data":
            raise ValueError(
                "undefined QBER requires key_status='no_key_insufficient_data'",
            )
        if (
            self.threshold_exceeded is True
            and self.key_status != "no_key_threshold_exceeded"
        ):
            raise ValueError(
                "an exceeded QBER threshold requires no_key_threshold_exceeded",
            )
        if (
            self.threshold_exceeded is not True
            and self.verification_status == "failed"
            and self.key_status != "no_key_verification_failed"
        ):
            raise ValueError(
                "failed verification requires key_status='no_key_verification_failed'",
            )
        if (
            self.key_status == "no_key_verification_failed"
            and self.verification_status != "failed"
        ):
            raise ValueError(
                "no_key_verification_failed requires failed verification",
            )
        if (
            self.key_status == "no_key_threshold_exceeded"
            and self.threshold_exceeded is not True
        ):
            raise ValueError(
                "no_key_threshold_exceeded requires an exceeded threshold",
            )
        if (
            self.key_status == "no_key_insufficient_data"
            and self.qber_defined
        ):
            raise ValueError(
                "no_key_insufficient_data requires undefined QBER",
            )
        if self.rate_estimate_status in {
            "available",
            "inconsistent_with_key_status",
        } and (self.rate_estimate_bps is None or self.rate_estimate_bps <= 0.0):
            raise ValueError(
                "an available rate estimate requires a positive rate_estimate_bps",
            )
        if (
            self.rate_estimate_status == "unavailable"
            and self.rate_estimate_bps is not None
        ):
            raise ValueError(
                "an unavailable rate estimate must not carry rate_estimate_bps",
            )
        incompatible_key_statuses = {
            "no_key_insufficient_data",
            "no_key_threshold_exceeded",
            "no_key_verification_failed",
            "no_extractable_key",
        }
        if (
            self.rate_estimate_bps is not None
            and self.rate_estimate_bps > 0.0
            and self.key_status in incompatible_key_statuses
            and self.rate_estimate_status != "inconsistent_with_key_status"
        ):
            raise ValueError(
                "a positive rate with no assessed key must be marked inconsistent",
            )
        if self.chsh_sample_size != sum(self.chsh_sample_size_by_term.values()):
            raise ValueError(
                "chsh_sample_size must equal the sum of chsh_sample_size_by_term",
            )
        if self.observed_chsh_s is not None and self.chsh_sample_size == 0:
            raise ValueError("observed_chsh_s requires a non-empty CHSH sample")
        if self.observed_threshold_exceeded is not None:
            if self.observed_chsh_s is None:
                raise ValueError(
                    "observed_threshold_exceeded requires observed_chsh_s",
                )
            if self.observed_threshold_exceeded != (
                self.observed_chsh_s > CHSH_CLASSICAL_BOUND
            ):
                raise ValueError(
                    "observed_threshold_exceeded must represent observed_chsh_s > 2",
                )
        is_e91 = self.protocol.lower() == "e91"
        has_chsh_payload = (
            self.observed_chsh_s is not None
            or self.chsh_sample_size > 0
            or bool(self.chsh_sample_size_by_term)
            or self.observed_threshold_exceeded is not None
            or self.conclusion_scope is not None
        )
        if not is_e91 and has_chsh_payload:
            raise ValueError("CHSH assessment fields are only valid for E91")
        if is_e91 and self.conclusion_scope != E91_CONCLUSION_SCOPE:
            raise ValueError(
                "E91 assessments require the diagnostic CHSH conclusion scope",
            )
        if self.chsh_sample_size > 0 and not self.chsh_sample_size_by_term:
            raise ValueError(
                "a CHSH sample requires per-term sample sizes",
            )
        if self.observed_chsh_s is not None and any(
            size == 0 for size in self.chsh_sample_size_by_term.values()
        ):
            raise ValueError(
                "observed_chsh_s requires a positive sample for every CHSH term",
            )

    def to_dict(self) -> JSONObject:
        data: JSONObject = {
            "protocol": self.protocol,
            "data_status": self.data_status,
            "qber_defined": self.qber_defined,
            "qber_value": self.qber_value,
            "sample_size": self.sample_size,
            "qber_method": self.qber_method,
            "threshold": self.threshold,
            "threshold_exceeded": self.threshold_exceeded,
            "threshold_decision_source": self.threshold_decision_source,
            "verification_status": self.verification_status,
            "key_status": self.key_status,
            "rate_estimate_status": self.rate_estimate_status,
            "rate_estimate_bps": self.rate_estimate_bps,
            "rate_estimate_method": self.rate_estimate_method,
            "security_scope": self.security_scope,
            "finite_key": self.finite_key,
            "composable": self.composable,
            "reason_codes": list(self.reason_codes),
            "reasons": list(self.reasons),
            "assumptions": list(self.assumptions),
        }
        if self.protocol.lower() == "e91" or self.conclusion_scope is not None:
            data.update(
                {
                    "observed_chsh_s": self.observed_chsh_s,
                    "chsh_sample_size": self.chsh_sample_size,
                    "chsh_sample_size_by_term": dict(
                        self.chsh_sample_size_by_term,
                    ),
                    "observed_threshold_exceeded": (
                        self.observed_threshold_exceeded
                    ),
                    "conclusion_scope": self.conclusion_scope,
                },
            )
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        if not isinstance(data, Mapping):
            raise TypeError("ResultAssessment payload must be a mapping")
        allowed = {
            "protocol",
            "data_status",
            "qber_defined",
            "qber_value",
            "sample_size",
            "qber_method",
            "threshold",
            "threshold_exceeded",
            "threshold_decision_source",
            "verification_status",
            "key_status",
            "rate_estimate_status",
            "rate_estimate_bps",
            "rate_estimate_method",
            "security_scope",
            "finite_key",
            "composable",
            "reason_codes",
            "reasons",
            "assumptions",
            "observed_chsh_s",
            "chsh_sample_size",
            "chsh_sample_size_by_term",
            "observed_threshold_exceeded",
            "conclusion_scope",
        }
        reject_unknown_fields("ResultAssessment", data, allowed)
        for name in ("reason_codes", "reasons", "assumptions"):
            if name in data and not isinstance(data[name], list):
                raise TypeError(f"assessment.{name} must be a JSON array")
        if "chsh_sample_size_by_term" in data and not isinstance(
            data["chsh_sample_size_by_term"],
            Mapping,
        ):
            raise TypeError(
                "assessment.chsh_sample_size_by_term must be a JSON object",
            )
        normalized = normalize_json_object(data, path="assessment")
        reason_codes = tuple(normalized.get("reason_codes", []))
        reasons = tuple(normalized.get("reasons", []))
        if not reasons:
            reasons = tuple(_reason_message(code) for code in reason_codes)
        return cls(
            protocol=normalized["protocol"],
            data_status=normalized["data_status"],
            qber_defined=normalized["qber_defined"],
            qber_value=normalized["qber_value"],
            sample_size=normalized["sample_size"],
            qber_method=normalized["qber_method"],
            threshold=normalized.get("threshold"),
            threshold_exceeded=normalized.get("threshold_exceeded"),
            threshold_decision_source=normalized["threshold_decision_source"],
            verification_status=normalized["verification_status"],
            key_status=normalized["key_status"],
            rate_estimate_status=normalized["rate_estimate_status"],
            rate_estimate_bps=normalized.get("rate_estimate_bps"),
            rate_estimate_method=normalized["rate_estimate_method"],
            security_scope=normalized.get("security_scope", SECURITY_SCOPE),
            finite_key=normalized.get("finite_key", False),
            composable=normalized.get("composable", False),
            reason_codes=reason_codes,
            reasons=reasons,
            assumptions=tuple(normalized.get("assumptions", [])),
            observed_chsh_s=normalized.get("observed_chsh_s"),
            chsh_sample_size=normalized.get("chsh_sample_size", 0),
            chsh_sample_size_by_term=normalized.get(
                "chsh_sample_size_by_term",
                {},
            ),
            observed_threshold_exceeded=normalized.get(
                "observed_threshold_exceeded",
            ),
            conclusion_scope=normalized.get("conclusion_scope"),
        )


def derive_result_assessment(
    scenario: Scenario,
    metrics: Metrics,
    *,
    classical: Mapping[str, Any],
    bell: Mapping[str, Any],
) -> ResultAssessment:
    """Derive an explicit assessment from schema-v1 metrics and diagnostics."""

    protocol = scenario.protocol.name.lower()
    reasons: list[str] = []
    assumptions = [
        "pedagogical simulation model",
        "asymptotic rate formula; no finite-key correction",
        "not a composable security proof",
    ]
    qber_value, qber_method, sample_size, qber_mismatch = _qber_evidence(
        metrics,
        classical,
    )
    if qber_mismatch:
        reasons.append("CLASSICAL_QBER_EVIDENCE_MISMATCH")
    if protocol != "e91" and metrics.chsh_s is not None:
        raise ValueError("metrics.chsh_s is only valid for an E91 result")
    if protocol != "e91" and _contains_chsh_evidence(bell):
        raise ValueError("Bell/CHSH evidence is only valid for an E91 result")
    qber_defined = qber_value is not None
    if not qber_defined:
        reasons.extend(("NO_SIFTED_BITS", "QBER_UNDEFINED"))
    elif qber_method == "revealed_sample":
        assumptions.append("revealed QBER sample; no confidence interval")
    elif qber_method == "full_sifted_key_diagnostic":
        assumptions.append(
            "QBER uses the full sifted key as a simulator-only diagnostic",
        )

    threshold = scenario.post_processing.qber_abort_threshold
    if "threshold" in classical:
        stored_threshold = _optional_probability(classical.get("threshold"))
        if stored_threshold != threshold:
            reasons.append("CLASSICAL_THRESHOLD_CONFIG_MISMATCH")
    threshold_exceeded, decision_source, decision_mismatch = _threshold_decision(
        qber_defined=qber_defined,
        qber_value=qber_value,
        threshold=threshold,
        metrics=metrics,
        classical=classical,
    )
    if decision_mismatch is not None:
        reasons.append(decision_mismatch)
    if threshold_exceeded:
        reasons.append("QBER_THRESHOLD_EXCEEDED")
    classical_decision = classical.get("threshold_exceeded", classical.get("abort"))
    if isinstance(classical_decision, bool) and classical_decision != metrics.abort:
        reasons.append("METRICS_CLASSICAL_ABORT_MISMATCH")

    verification_status = _verification_status(
        metrics=metrics,
        classical=classical,
        qber_defined=qber_defined,
        threshold_exceeded=threshold_exceeded,
        protocol=protocol,
    )
    if verification_status == "failed":
        reasons.append("VERIFICATION_FAILED")

    rate_bps = metrics.secret_key_rate_bps
    key_status = _key_status(
        protocol=protocol,
        qber_defined=qber_defined,
        threshold_exceeded=threshold_exceeded,
        verification_status=verification_status,
        final_key_length=_optional_non_negative_int(classical.get("final_key_length")),
        rate_bps=rate_bps,
    )
    if key_status == "no_extractable_key":
        reasons.append("NO_EXTRACTABLE_KEY")

    rate_status = "available" if rate_bps > 0.0 else "unavailable"
    incompatible_key_statuses = {
        "no_key_insufficient_data",
        "no_key_threshold_exceeded",
        "no_key_verification_failed",
        "no_extractable_key",
    }
    if rate_bps > 0.0 and key_status in incompatible_key_statuses:
        rate_status = "inconsistent_with_key_status"
        reasons.append("LEGACY_RATE_INCONSISTENT_WITH_KEY_STATUS")

    observed_chsh_s: float | None = None
    chsh_sample_size = 0
    chsh_by_term: dict[str, int] = {}
    observed_threshold_exceeded: bool | None = None
    conclusion_scope: str | None = None
    if protocol == "e91":
        conclusion_scope = E91_CONCLUSION_SCOPE
        assumptions.extend(
            (
                "CHSH diagnostic assumes fair sampling of detected coincidences",
                "no statistical significance or confidence interval is computed",
                (
                    "detected-coincidence post-selection does not close "
                    "detection or locality loopholes"
                ),
                "not a device-independent security certification",
            ),
        )
        chsh_by_term, observed_chsh_s = _chsh_evidence_from_rows(
            scenario,
            bell,
        )
        chsh_sample_size = sum(chsh_by_term.values())
        if not scenario.e91.chsh_estimation_enabled:
            observed_chsh_s = None
            reasons.append("CHSH_DISABLED")
            if not _bell_chsh_evidence_matches(
                bell,
                observed_chsh_s=None,
                sample_size=chsh_sample_size,
                sample_size_by_term=chsh_by_term,
                chsh_enabled_expected=False,
            ):
                reasons.append("BELL_CHSH_EVIDENCE_MISMATCH")
            if metrics.chsh_s is not None:
                reasons.append("METRICS_CHSH_EVIDENCE_MISMATCH")
        elif observed_chsh_s is not None:
            observed_threshold_exceeded = observed_chsh_s > CHSH_CLASSICAL_BOUND
            if not _bell_chsh_evidence_matches(
                bell,
                observed_chsh_s=observed_chsh_s,
                sample_size=chsh_sample_size,
                sample_size_by_term=chsh_by_term,
                chsh_enabled_expected=True,
            ):
                reasons.append("BELL_CHSH_EVIDENCE_MISMATCH")
            if not _optional_float_matches(metrics.chsh_s, observed_chsh_s):
                reasons.append("METRICS_CHSH_EVIDENCE_MISMATCH")
        else:
            reasons.append("CHSH_UNAVAILABLE")
            if not _bell_chsh_evidence_matches(
                bell,
                observed_chsh_s=None,
                sample_size=chsh_sample_size,
                sample_size_by_term=chsh_by_term,
                chsh_enabled_expected=True,
            ):
                reasons.append("BELL_CHSH_EVIDENCE_MISMATCH")
            if metrics.chsh_s is not None:
                reasons.append("METRICS_CHSH_EVIDENCE_MISMATCH")

    unique_reason_codes = tuple(dict.fromkeys(reasons))
    return ResultAssessment(
        protocol=protocol,
        data_status="available" if qber_defined else "insufficient_data",
        qber_defined=qber_defined,
        qber_value=qber_value,
        sample_size=sample_size,
        qber_method=qber_method,
        threshold=threshold,
        threshold_exceeded=threshold_exceeded,
        threshold_decision_source=decision_source,
        verification_status=verification_status,
        key_status=key_status,
        rate_estimate_status=rate_status,
        rate_estimate_bps=rate_bps if rate_bps > 0.0 else None,
        rate_estimate_method="pedagogical_bb84_asymptotic_qber_fraction",
        reason_codes=unique_reason_codes,
        reasons=tuple(_reason_message(code) for code in unique_reason_codes),
        assumptions=tuple(dict.fromkeys(assumptions)),
        observed_chsh_s=observed_chsh_s,
        chsh_sample_size=chsh_sample_size,
        chsh_sample_size_by_term=chsh_by_term,
        observed_threshold_exceeded=observed_threshold_exceeded,
        conclusion_scope=conclusion_scope,
    )


def _normalized_strings(name: str, values: Any) -> tuple[str, ...]:
    if not isinstance(values, tuple | list):
        raise TypeError(f"{name} must be a tuple or list of strings")
    return tuple(
        require_non_empty_str(f"{name}[{index}]", value)
        for index, value in enumerate(values)
    )


def _reason_message(code: str) -> str:
    return REASON_MESSAGES.get(code, code.replace("_", " ").capitalize() + ".")


def _optional_probability(value: Any) -> float | None:
    if value is None:
        return None
    return require_optional_probability("threshold", value)


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    return require_non_negative_int("final_key_length", value)


def _qber_evidence(
    metrics: Metrics,
    classical: Mapping[str, Any],
) -> tuple[float | None, str, int, bool]:
    if metrics.sifted == 0:
        inconsistent = classical.get("qber_defined") is True
        return None, "unavailable", 0, inconsistent
    sample_size_value = classical.get("qber_sample_size", 0)
    sample_size = require_non_negative_int(
        "qber_sample_size",
        sample_size_value,
    )
    if sample_size > metrics.sifted:
        raise ValueError("qber_sample_size must not exceed metrics.sifted")
    method = classical.get("qber_method")
    if method not in QBER_METHODS:
        method = "revealed_sample" if sample_size > 0 else "full_sifted_key_diagnostic"
    estimated = classical.get("estimated_qber")
    if method == "revealed_sample":
        if sample_size == 0:
            raise ValueError("revealed_sample QBER requires qber_sample_size > 0")
        if not isinstance(estimated, int | float) or isinstance(estimated, bool):
            raise TypeError("revealed_sample QBER requires numeric estimated_qber")
        qber_value = require_optional_probability("estimated_qber", estimated)
        return qber_value, method, sample_size, classical.get("qber_defined") is False

    aggregate_qber = metrics.errors / metrics.sifted
    mismatch = classical.get("qber_defined") is False
    if isinstance(estimated, int | float) and not isinstance(estimated, bool):
        stored_qber = require_optional_probability("estimated_qber", estimated)
        mismatch = mismatch or not math.isclose(
            stored_qber,
            aggregate_qber,
            rel_tol=1e-12,
            abs_tol=1e-12,
        )
    elif estimated is not None:
        raise TypeError("estimated_qber must be a number or null")
    return aggregate_qber, "full_sifted_key_diagnostic", metrics.sifted, mismatch


def _threshold_decision(
    *,
    qber_defined: bool,
    qber_value: float | None,
    threshold: float | None,
    metrics: Metrics,
    classical: Mapping[str, Any],
) -> tuple[bool | None, str, str | None]:
    if threshold is None:
        return None, "disabled", None
    if not qber_defined or qber_value is None:
        return None, "unavailable", None
    evidence_decision = qber_value > threshold
    explicit = classical.get("threshold_exceeded", classical.get("abort"))
    if isinstance(explicit, bool):
        source = classical.get("threshold_decision_source")
        if source not in {"classical_estimate", "metrics_legacy"}:
            source = "classical_estimate"
        mismatch = (
            "CLASSICAL_THRESHOLD_EVIDENCE_MISMATCH"
            if explicit != evidence_decision
            else None
        )
        return evidence_decision, source, mismatch
    mismatch = (
        "METRICS_THRESHOLD_EVIDENCE_MISMATCH"
        if metrics.abort != evidence_decision
        else None
    )
    return evidence_decision, "metrics_legacy", mismatch


def _verification_status(
    *,
    metrics: Metrics,
    classical: Mapping[str, Any],
    qber_defined: bool,
    threshold_exceeded: bool | None,
    protocol: str,
) -> str:
    if not qber_defined or metrics.sifted == 0:
        return "not_applicable"
    if threshold_exceeded is True:
        return "not_performed"
    candidate_length = classical.get("candidate_key_length")
    if candidate_length == 0:
        return "not_applicable"
    explicit = classical.get("verification_status")
    if isinstance(explicit, str) and explicit in VERIFICATION_STATUSES:
        return explicit
    legacy = classical.get("verification_passed")
    if isinstance(legacy, bool):
        return "passed" if legacy else "failed"
    if protocol == "e91":
        return "not_performed"
    return "unknown"


def _key_status(
    *,
    protocol: str,
    qber_defined: bool,
    threshold_exceeded: bool | None,
    verification_status: str,
    final_key_length: int | None,
    rate_bps: float,
) -> str:
    if not qber_defined:
        return "no_key_insufficient_data"
    if threshold_exceeded is True:
        return "no_key_threshold_exceeded"
    if verification_status == "failed":
        return "no_key_verification_failed"
    if final_key_length is not None:
        return (
            "estimated_key_available"
            if final_key_length > 0
            else "no_extractable_key"
        )
    if protocol == "e91":
        return "estimated_key_available" if rate_bps > 0.0 else "no_extractable_key"
    return "unknown"


def _contains_chsh_evidence(bell: Mapping[str, Any]) -> bool:
    return any(
        name in bell
        for name in {
            "bell_violation",
            "chsh_enabled",
            "chsh_s",
            "observed_chsh_s",
            "chsh_sample_size",
            "chsh_sample_size_by_term",
            "observed_threshold_exceeded",
            "classical_bound",
            "quantum_bound",
            "conclusion_scope",
            "setting_rows",
        }
    )


def _chsh_evidence_from_rows(
    scenario: Scenario,
    bell: Mapping[str, Any],
) -> tuple[dict[str, int], float | None]:
    rows = bell.get("setting_rows")
    if not isinstance(rows, list | tuple):
        return {}, None
    rows_by_pair: dict[tuple[int, int], Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("used_for_chsh") is not True:
            continue
        alice_setting = row.get("alice_setting")
        bob_setting = row.get("bob_setting")
        if (
            not isinstance(alice_setting, int)
            or isinstance(alice_setting, bool)
            or not isinstance(bob_setting, int)
            or isinstance(bob_setting, bool)
        ):
            continue
        pair = (alice_setting, bob_setting)
        if pair in rows_by_pair:
            raise ValueError(f"duplicate CHSH setting row for A{pair[0]}/B{pair[1]}")
        rows_by_pair[pair] = row

    required_pairs = [
        (alice, bob) for alice, bob, _coefficient in scenario.e91.chsh_terms
    ]
    if len(set(required_pairs)) != len(required_pairs):
        raise ValueError("E91 chsh_terms must reference unique setting pairs")
    unexpected_pairs = set(rows_by_pair) - set(required_pairs)
    if unexpected_pairs:
        unexpected = ", ".join(
            f"A{alice}/B{bob}" for alice, bob in sorted(unexpected_pairs)
        )
        raise ValueError(f"unexpected rows marked used_for_chsh: {unexpected}")

    sample_sizes: dict[str, int] = {}
    correlations: dict[tuple[int, int], float] = {}
    for alice, bob, _coefficient in scenario.e91.chsh_terms:
        pair = (alice, bob)
        row = rows_by_pair.get(pair)
        if row is None:
            return sample_sizes, None
        label = f"A{alice}/B{bob}"
        coincidences = _row_count(row, "coincidences", label)
        attempts = _optional_row_count(row, "attempts", label)
        if attempts is not None and coincidences > attempts:
            raise ValueError(f"CHSH row {label} coincidences exceeds attempts")
        sample_sizes[label] = coincidences
        same = _optional_row_count(row, "same", label)
        different = _optional_row_count(row, "different", label)
        if same is None or different is None or same + different != coincidences:
            if (
                same is not None
                and different is not None
                and same + different > coincidences
            ):
                raise ValueError(
                    f"CHSH row {label} same+different exceeds coincidences",
                )
            continue
        if coincidences > 0:
            correlations[pair] = (same - different) / coincidences

    if (
        not scenario.e91.chsh_estimation_enabled
        or len(correlations) != len(required_pairs)
        or any(size == 0 for size in sample_sizes.values())
    ):
        return sample_sizes, None
    chsh_s = abs(
        sum(
            coefficient * correlations[(alice, bob)]
            for alice, bob, coefficient in scenario.e91.chsh_terms
        ),
    )
    return sample_sizes, chsh_s


def _row_count(row: Mapping[str, Any], name: str, label: str) -> int:
    value = row.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"CHSH row {label} field {name!r} must be an integer")
    if value < 0:
        raise ValueError(f"CHSH row {label} field {name!r} must be non-negative")
    return value


def _optional_row_count(
    row: Mapping[str, Any],
    name: str,
    label: str,
) -> int | None:
    if name not in row:
        return None
    return _row_count(row, name, label)


def _bell_chsh_evidence_matches(
    bell: Mapping[str, Any],
    *,
    observed_chsh_s: float | None,
    sample_size: int,
    sample_size_by_term: Mapping[str, int],
    chsh_enabled_expected: bool,
) -> bool:
    matches = True
    stored_values: list[float] = []
    for name in ("chsh_s", "observed_chsh_s"):
        if name not in bell or bell[name] is None:
            continue
        value = bell[name]
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise TypeError(f"bell.{name} must be a number or null")
        normalized = float(value)
        if not math.isfinite(normalized) or not 0.0 <= normalized <= 4.0:
            raise ValueError(f"bell.{name} must be finite and between 0 and 4")
        stored_values.append(normalized)
    if observed_chsh_s is None:
        matches = not stored_values
    elif not stored_values or any(
        not _optional_float_matches(value, observed_chsh_s)
        for value in stored_values
    ):
        matches = False

    if "chsh_sample_size" in bell:
        stored_size = bell["chsh_sample_size"]
        if not isinstance(stored_size, int) or isinstance(stored_size, bool):
            raise TypeError("bell.chsh_sample_size must be an integer")
        if stored_size < 0:
            raise ValueError("bell.chsh_sample_size must be non-negative")
        if stored_size != sample_size:
            matches = False
    if "chsh_sample_size_by_term" in bell:
        stored_by_term = bell["chsh_sample_size_by_term"]
        if not isinstance(stored_by_term, Mapping):
            raise TypeError("bell.chsh_sample_size_by_term must be a JSON object")
        normalized_by_term = {
            str(name): _row_count(
                {"count": value},
                "count",
                str(name),
            )
            for name, value in stored_by_term.items()
        }
        if normalized_by_term != dict(sample_size_by_term):
            matches = False
    if "observed_threshold_exceeded" in bell:
        stored_threshold = bell["observed_threshold_exceeded"]
        expected_threshold = (
            None
            if observed_chsh_s is None
            else observed_chsh_s > CHSH_CLASSICAL_BOUND
        )
        if stored_threshold is not None and not isinstance(stored_threshold, bool):
            raise TypeError("bell.observed_threshold_exceeded must be boolean or null")
        if stored_threshold != expected_threshold:
            matches = False
    if "bell_violation" in bell:
        legacy_threshold = bell["bell_violation"]
        if not isinstance(legacy_threshold, bool):
            raise TypeError("bell.bell_violation must be a boolean")
        expected_threshold = (
            False
            if observed_chsh_s is None
            else observed_chsh_s > CHSH_CLASSICAL_BOUND
        )
        if legacy_threshold != expected_threshold:
            matches = False
    if "chsh_enabled" in bell:
        chsh_enabled = bell["chsh_enabled"]
        if not isinstance(chsh_enabled, bool):
            raise TypeError("bell.chsh_enabled must be a boolean")
        if chsh_enabled != chsh_enabled_expected:
            matches = False
    if "classical_bound" in bell:
        classical_bound = bell["classical_bound"]
        if not isinstance(classical_bound, int | float) or isinstance(
            classical_bound,
            bool,
        ):
            raise TypeError("bell.classical_bound must be a number")
        if not math.isclose(
            float(classical_bound),
            CHSH_CLASSICAL_BOUND,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            matches = False
    if "conclusion_scope" in bell and bell["conclusion_scope"] not in {
        None,
        E91_CONCLUSION_SCOPE,
    }:
        matches = False
    return matches


def _optional_float_matches(value: float | None, expected: float) -> bool:
    return value is not None and math.isclose(
        value,
        expected,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )
