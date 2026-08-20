"""Serializable simulation result containers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from typing import Any, Self

from qiskit_qkd._json import (
    JSONObject,
    dumps_pretty,
    loads_object,
    normalize_json_object,
)
from qiskit_qkd._validation import (
    reject_unknown_fields,
    require_bool,
    require_non_empty_str,
)
from qiskit_qkd.config import Scenario, effective_parameter_snapshot
from qiskit_qkd.provenance import PACKAGE_VERSION as __version__
from qiskit_qkd.provenance import (
    RUNTIME_PROVENANCE_FIELDS,
    runtime_provenance,
    trusted_backend_name,
)

from .assessment import ResultAssessment, derive_result_assessment
from .event import Event
from .metrics import Metrics

LEGACY_RESULT_SCHEMA_VERSION = 1
RESULT_SCHEMA_VERSION = 2
SUPPORTED_RESULT_SCHEMA_VERSIONS = {
    LEGACY_RESULT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
}
_RESERVED_PROVENANCE_FIELDS = {
    "schema_version",
    "library_version",
    "seed",
    "scenario_digest",
    "effective_model",
    "rng",
} | (RUNTIME_PROVENANCE_FIELDS - {"backend"})
_DEFENSIVE_JSON_FIELDS = {
    "provenance",
    "qiskit",
    "classical",
    "decoy",
    "bell",
}
_ARCHIVED_PROVENANCE_TOKEN = object()


def _strip_adversary_fields(value: Any) -> Any:
    """Copy JSON-like data while omitting simulator-side Eve metadata.

    ``to_dict`` remains the compatibility/archive representation.  Public
    observed views use this filter so adversary configuration and traces do
    not become apparent protocol inputs merely because a result was exported.
    ``event_sample`` is intentionally retained; only keys explicitly naming
    Eve (or the eavesdropper configuration) are removed.
    """

    if isinstance(value, Mapping):
        return {
            key: _strip_adversary_fields(item)
            for key, item in value.items()
            if not (
                isinstance(key, str)
                and (key.startswith("eve_") or key == "eavesdropper")
            )
        }
    if isinstance(value, list):
        return [_strip_adversary_fields(item) for item in value]
    return value


def default_provenance(
    scenario: Scenario,
    *,
    library_version: str = __version__,
    backend: str = "unknown",
    backend_source: str = "unavailable",
) -> JSONObject:
    provenance: JSONObject = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "library_version": require_non_empty_str(
            "library_version",
            library_version,
        ),
        "seed": scenario.seed,
        "scenario_digest": scenario.digest(),
        "rng": "python.random.Random",
    }
    provenance["effective_model"] = effective_parameter_snapshot(scenario)
    provenance.update(
        runtime_provenance(
            backend=backend,
            backend_source=backend_source,
        )
    )
    return provenance


def _merge_provenance(
    scenario: Scenario,
    value: Mapping[str, Any],
    *,
    library_version: str,
) -> JSONObject:
    """Merge provenance without allowing authoritative fields to be spoofed."""

    trusted_backend = trusted_backend_name(value)
    supplied_backend = value.get("backend")
    if trusted_backend is not None:
        backend = trusted_backend
        backend_source = "runtime"
    elif isinstance(supplied_backend, str) and supplied_backend.strip():
        backend = supplied_backend.strip()
        backend_source = "producer_supplied"
    else:
        backend = "unknown"
        backend_source = "unavailable"
    authoritative = default_provenance(
        scenario,
        library_version=library_version,
        backend=backend,
        backend_source=backend_source,
    )
    supplied = normalize_json_object(value, path="provenance")
    previous_conflicts = supplied.pop("reserved_field_conflicts", None)
    conflicts: JSONObject = {}
    if isinstance(previous_conflicts, dict):
        conflicts.update(previous_conflicts)
    elif previous_conflicts is not None:
        conflicts["legacy_reserved_field_conflicts"] = {
            "provided": previous_conflicts,
            "authoritative": None,
        }

    for name in _RESERVED_PROVENANCE_FIELDS:
        if name not in authoritative or name not in supplied:
            continue
        if supplied[name] != authoritative[name]:
            conflicts[name] = {
                "provided": supplied[name],
                "authoritative": authoritative[name],
            }

    merged = dict(authoritative)
    merged.update(
        {
            name: item
            for name, item in supplied.items()
            if name not in _RESERVED_PROVENANCE_FIELDS
        },
    )
    merged["backend"] = backend
    merged["backend_source"] = backend_source
    if conflicts:
        merged["reserved_field_conflicts"] = conflicts
    return merged


def _archived_provenance(
    scenario: Scenario,
    value: Mapping[str, Any],
    *,
    source_schema_version: int,
    envelope_library_version: str | None,
    assessment_source: str | None,
) -> JSONObject:
    """Preserve producer metadata while labelling archive-load inferences.

    In particular, loading an old result must not claim that the current
    library version or today's effective-model resolver produced it.
    """

    provenance = normalize_json_object(value, path="provenance")
    existing_audit = provenance.get("archive_load")
    had_existing_audit = isinstance(existing_audit, Mapping)
    audit: JSONObject = (
        normalize_json_object(existing_audit, path="provenance.archive_load")
        if isinstance(existing_audit, Mapping)
        else {}
    )
    if existing_audit is not None and not isinstance(existing_audit, Mapping):
        audit["previous_archive_load_value"] = normalize_json_object(
            {"value": existing_audit},
            path="provenance.archive_load",
        )["value"]
    original_schema = audit.get("source_schema_version", source_schema_version)
    if (
        not isinstance(original_schema, int)
        or isinstance(original_schema, bool)
        or original_schema not in SUPPORTED_RESULT_SCHEMA_VERSIONS
    ):
        original_schema = source_schema_version
    audit["source_schema_version"] = original_schema

    inferred = _mapping_copy(audit.get("inferred_fields"))
    unavailable = _string_list_copy(audit.get("unavailable_fields"))
    conflicts = _mapping_copy(audit.get("evidence_conflicts"))
    if assessment_source is not None:
        audit["assessment_source"] = assessment_source

    if "schema_version" not in provenance:
        provenance["schema_version"] = original_schema
        inferred["schema_version"] = "result envelope"
    elif provenance["schema_version"] != source_schema_version:
        conflicts["schema_version"] = {
            "provided": provenance["schema_version"],
            "envelope_value": source_schema_version,
        }
    if "library_version" not in provenance and envelope_library_version is not None:
        provenance["library_version"] = envelope_library_version
        inferred["library_version"] = "result envelope"
    if "seed" not in provenance:
        provenance["seed"] = scenario.seed
        inferred["seed"] = "serialized scenario"
    elif provenance["seed"] != scenario.seed:
        conflicts["seed"] = {
            "provided": provenance["seed"],
            "scenario_value": scenario.seed,
        }
    scenario_digest = scenario.digest()
    if "scenario_digest" not in provenance:
        provenance["scenario_digest"] = scenario_digest
        inferred["scenario_digest"] = "serialized scenario"
    elif provenance["scenario_digest"] != scenario_digest:
        conflicts["scenario_digest"] = {
            "provided": provenance["scenario_digest"],
            "scenario_value": scenario_digest,
        }
    if (
        envelope_library_version is not None
        and "library_version" in provenance
        and provenance["library_version"] != envelope_library_version
    ):
        conflicts["library_version"] = {
            "provided": provenance["library_version"],
            "envelope_value": envelope_library_version,
        }
    if "effective_model" not in provenance and "effective_model" not in unavailable:
        unavailable.append("effective_model")
    for name in sorted(RUNTIME_PROVENANCE_FIELDS):
        if name not in provenance and name not in unavailable:
            unavailable.append(name)

    if inferred:
        audit["inferred_fields"] = inferred
    if unavailable:
        audit["unavailable_fields"] = unavailable
    if conflicts:
        audit["evidence_conflicts"] = conflicts
    if (
        had_existing_audit
        or assessment_source is not None
        or inferred
        or unavailable
        or conflicts
    ):
        provenance["archive_load"] = audit
    return provenance


def _mapping_copy(value: Any) -> JSONObject:
    return (
        normalize_json_object(value, path="archive metadata")
        if isinstance(value, Mapping)
        else {}
    )


def _string_list_copy(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Scenario, metrics, provenance, and sampled events from one run.

    JSON-object fields are exposed as defensive ``dict``/``list`` copies so
    callers cannot mutate a frozen result through a nested container alias.
    """

    scenario: Scenario
    metrics: Metrics
    provenance: JSONObject = field(default_factory=dict)
    qiskit: JSONObject = field(default_factory=dict)
    classical: JSONObject = field(default_factory=dict)
    decoy: JSONObject = field(default_factory=dict)
    bell: JSONObject = field(default_factory=dict)
    library_version: str = __version__
    event_sample: tuple[Event, ...] = field(default_factory=tuple)
    aggregated: bool = True
    assessment: ResultAssessment | Mapping[str, Any] | None = None
    _provenance_load_token: InitVar[object | None] = None

    def __getattribute__(self, name: str) -> Any:
        value = object.__getattribute__(self, name)
        if name in _DEFENSIVE_JSON_FIELDS:
            return normalize_json_object(value, path=name)
        return value

    def __post_init__(self, _provenance_load_token: object | None) -> None:
        if self.metrics.pulses != self.scenario.pulses:
            raise ValueError("metrics.pulses must match scenario.pulses")
        library_version = require_non_empty_str(
            "library_version",
            self.library_version,
        )
        object.__setattr__(self, "library_version", library_version)
        if (
            _provenance_load_token is not None
            and _provenance_load_token is not _ARCHIVED_PROVENANCE_TOKEN
        ):
            raise TypeError("_provenance_load_token is reserved for from_dict()")
        is_archived_load = _provenance_load_token is _ARCHIVED_PROVENANCE_TOKEN
        normalized_provenance = (
            _merge_provenance(
                self.scenario,
                object.__getattribute__(self, "provenance"),
                library_version=library_version,
            )
            if not is_archived_load
            else normalize_json_object(
                object.__getattribute__(self, "provenance"),
                path="provenance",
            )
        )
        object.__setattr__(
            self,
            "provenance",
            normalized_provenance,
        )
        object.__setattr__(
            self,
            "qiskit",
            normalize_json_object(self.qiskit, path="qiskit"),
        )
        object.__setattr__(
            self,
            "classical",
            normalize_json_object(self.classical, path="classical"),
        )
        object.__setattr__(
            self,
            "decoy",
            normalize_json_object(self.decoy, path="decoy"),
        )
        object.__setattr__(
            self,
            "bell",
            normalize_json_object(self.bell, path="bell"),
        )
        derived_assessment = derive_result_assessment(
            self.scenario,
            self.metrics,
            classical=self.classical,
            bell=self.bell,
        )
        if self.assessment is None:
            assessment = derived_assessment
        elif isinstance(self.assessment, ResultAssessment):
            assessment = self.assessment
        elif isinstance(self.assessment, Mapping):
            assessment = ResultAssessment.from_dict(self.assessment)
        else:
            raise TypeError("assessment must be a ResultAssessment, mapping, or None")
        supplied_assessment = assessment.to_dict()
        authoritative_assessment = derived_assessment.to_dict()
        if supplied_assessment != authoritative_assessment:
            differing_fields = sorted(
                name
                for name in set(supplied_assessment) | set(authoritative_assessment)
                if supplied_assessment.get(name)
                != authoritative_assessment.get(name)
            )
            names = ", ".join(differing_fields)
            raise ValueError(
                "assessment disagrees with result evidence in field(s): " + names,
            )
        object.__setattr__(self, "assessment", derived_assessment)
        object.__setattr__(self, "event_sample", tuple(self.event_sample))
        object.__setattr__(
            self,
            "aggregated",
            require_bool("aggregated", self.aggregated),
        )
        if (
            not self.scenario.store_full_event_log
            and len(self.event_sample) > self.scenario.event_sample_size
        ):
            raise ValueError("event_sample exceeds scenario.event_sample_size")

    def to_dict(
        self,
        *,
        schema_version: int = RESULT_SCHEMA_VERSION,
    ) -> JSONObject:
        schema_version = _require_result_schema_version(schema_version)
        provenance = normalize_json_object(self.provenance, path="provenance")
        if schema_version == LEGACY_RESULT_SCHEMA_VERSION:
            provenance["schema_version"] = LEGACY_RESULT_SCHEMA_VERSION
        payload: JSONObject = {
            "schema_version": schema_version,
            "library_version": self.library_version,
            "scenario": normalize_json_object(
                self.scenario.to_dict(),
                path="scenario",
            ),
            "metrics": normalize_json_object(self.metrics.to_dict(), path="metrics"),
            "provenance": provenance,
            "qiskit": normalize_json_object(self.qiskit, path="qiskit"),
            "classical": normalize_json_object(self.classical, path="classical"),
            "decoy": normalize_json_object(self.decoy, path="decoy"),
            "bell": normalize_json_object(self.bell, path="bell"),
            "event_sample": [
                normalize_json_object(event.to_dict(), path="event_sample")
                for event in self.event_sample
            ],
            "aggregated": self.aggregated,
        }
        if schema_version == RESULT_SCHEMA_VERSION:
            payload["assessment"] = self.assessment.to_dict()
        return payload

    def to_legacy_dict(self) -> JSONObject:
        """Export the exact schema-v1 envelope without v2-only assessment."""

        return self.to_dict(schema_version=LEGACY_RESULT_SCHEMA_VERSION)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        if not isinstance(data, Mapping):
            raise TypeError("SimulationResult payload must be a mapping")
        reject_unknown_fields(
            "SimulationResult",
            data,
            {
                "schema_version",
                "library_version",
                "scenario",
                "metrics",
                "provenance",
                "qiskit",
                "classical",
                "decoy",
                "bell",
                "assessment",
                "event_sample",
                "aggregated",
            },
        )
        schema_version = _require_result_schema_version(
            data.get("schema_version", LEGACY_RESULT_SCHEMA_VERSION),
        )
        if schema_version == RESULT_SCHEMA_VERSION:
            if "assessment" not in data:
                raise ValueError("schema-v2 result requires an assessment field")
            if data["assessment"] is None:
                raise ValueError("schema-v2 assessment must not be null")
            if not isinstance(data["assessment"], Mapping):
                raise TypeError("schema-v2 assessment must be a JSON object")
        assessment = data.get("assessment")
        if assessment is not None and not isinstance(assessment, Mapping):
            raise TypeError("assessment must be a JSON object or null")
        scenario_data = _require_mapping_field(data, "scenario")
        metrics_data = _require_mapping_field(data, "metrics")
        scenario = Scenario.from_dict(scenario_data)
        metrics = Metrics.from_dict(metrics_data)
        provenance_data = _optional_mapping_field(data, "provenance")
        envelope_library_version = _optional_library_version(data)
        library_version = _archived_library_version(
            envelope_library_version,
            provenance_data,
        )
        event_sample_data = data.get("event_sample", [])
        if not isinstance(event_sample_data, list):
            raise TypeError("event_sample must be a JSON array")
        return cls(
            scenario=scenario,
            metrics=metrics,
            provenance=_archived_provenance(
                scenario,
                provenance_data,
                source_schema_version=schema_version,
                envelope_library_version=envelope_library_version,
                assessment_source=_legacy_assessment_source(
                    schema_version,
                    data,
                ),
            ),
            qiskit=_optional_mapping_field(data, "qiskit"),
            classical=_optional_mapping_field(data, "classical"),
            decoy=_optional_mapping_field(data, "decoy"),
            bell=_optional_mapping_field(data, "bell"),
            assessment=assessment,
            library_version=library_version,
            event_sample=tuple(
                Event.from_dict(event_data)
                for event_data in event_sample_data
            ),
            aggregated=data.get("aggregated", True),
            _provenance_load_token=_ARCHIVED_PROVENANCE_TOKEN,
        )

    def to_json(
        self,
        *,
        schema_version: int = RESULT_SCHEMA_VERSION,
    ) -> str:
        return dumps_pretty(self.to_dict(schema_version=schema_version))

    def to_legacy_json(self) -> str:
        """Export a schema-v1 JSON envelope for legacy readers."""

        return self.to_json(schema_version=LEGACY_RESULT_SCHEMA_VERSION)

    def to_observed_dict(
        self,
        *,
        schema_version: int = RESULT_SCHEMA_VERSION,
    ) -> JSONObject:
        """Serialize only observations available to Alice and Bob.

        This is an additive, explicit view.  The default :meth:`to_dict`
        remains unchanged for legacy archives and simulator-side analysis;
        callers that publish or hand a result to protocol participants should
        use this method so Eve fields/configuration are omitted.
        """

        payload = self.to_dict(schema_version=schema_version)
        return _strip_adversary_fields(payload)

    def to_observed_json(
        self,
        *,
        schema_version: int = RESULT_SCHEMA_VERSION,
    ) -> str:
        """Serialize the Alice/Bob observed view as JSON."""

        return dumps_pretty(self.to_observed_dict(schema_version=schema_version))

    # Short aliases make the separation discoverable without changing the
    # legacy schema API.
    observed_dict = to_observed_dict
    observed_json = to_observed_json

    @property
    def observed(self) -> JSONObject:
        """Return a defensive Alice/Bob-only result mapping."""

        return self.to_observed_dict()

    def to_internal_diagnostics_dict(self) -> JSONObject:
        """Serialize simulator diagnostics, including Eve traces/configuration."""

        event_sample = [
            normalize_json_object(event.to_dict(), path="event_sample")
            for event in self.event_sample
        ]
        return {
            "scenario": normalize_json_object(self.scenario.to_dict(), path="scenario"),
            "metrics": normalize_json_object(self.metrics.to_dict(), path="metrics"),
            # Flat aliases make simulator reports convenient while the nested
            # metrics object preserves the legacy shape.
            "eve_intercepted_fraction": self.metrics.eve_intercepted_fraction,
            "eve_information_estimate": self.metrics.eve_information_estimate,
            "provenance": normalize_json_object(self.provenance, path="provenance"),
            "qiskit": normalize_json_object(self.qiskit, path="qiskit"),
            "classical": normalize_json_object(self.classical, path="classical"),
            "decoy": normalize_json_object(self.decoy, path="decoy"),
            "bell": normalize_json_object(self.bell, path="bell"),
            "event_sample": event_sample,
            "events": event_sample,
            "assessment": self.assessment.to_dict(),
        }

    @property
    def internal_diagnostics(self) -> JSONObject:
        """Return simulator-side diagnostics, including Eve information."""

        return self.to_internal_diagnostics_dict()

    def authoritative_metrics(self) -> JSONObject:
        """Return the public evidence-backed metric interpretation.

        The implementation is imported lazily to keep the results package
        independent from the analysis package at import time.
        """

        from qiskit_qkd.analysis.metrics import extract_authoritative_metrics

        return extract_authoritative_metrics(self)

    @classmethod
    def from_json(cls, payload: str) -> Self:
        return cls.from_dict(loads_object(payload))

    def summary(self) -> JSONObject:
        return {
            "library_version": self.library_version,
            "seed": self.scenario.seed,
            "scenario_digest": self.scenario.digest(),
            "metrics": self.metrics.to_dict(),
            "classical": normalize_json_object(self.classical, path="classical"),
            "decoy": normalize_json_object(self.decoy, path="decoy"),
            "bell": normalize_json_object(self.bell, path="bell"),
            "assessment": self.assessment.to_dict(),
            "provenance": normalize_json_object(
                self.provenance,
                path="provenance",
            ),
            "qiskit": normalize_json_object(self.qiskit, path="qiskit"),
            "event_sample_size": len(self.event_sample),
            "aggregated": self.aggregated,
        }


def _require_result_schema_version(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("result schema_version must be an integer")
    if value not in SUPPORTED_RESULT_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported result schema_version: {value}")
    return value


def _require_mapping_field(
    data: Mapping[str, Any],
    name: str,
) -> Mapping[str, Any]:
    if name not in data:
        raise ValueError(f"SimulationResult requires field {name!r}")
    value = data[name]
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a JSON object")
    return value


def _optional_mapping_field(
    data: Mapping[str, Any],
    name: str,
) -> Mapping[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a JSON object")
    return value


def _optional_library_version(data: Mapping[str, Any]) -> str | None:
    if "library_version" not in data:
        return None
    return require_non_empty_str("library_version", data["library_version"])


def _archived_library_version(
    envelope_library_version: str | None,
    provenance: Mapping[str, Any],
) -> str:
    if envelope_library_version is not None:
        return envelope_library_version
    producer_version = provenance.get("library_version")
    if isinstance(producer_version, str) and producer_version.strip():
        return producer_version.strip()
    return "unknown"


def _legacy_assessment_source(
    schema_version: int,
    data: Mapping[str, Any],
) -> str | None:
    if schema_version != LEGACY_RESULT_SCHEMA_VERSION:
        return None
    if "assessment" not in data:
        return "derived_from_schema_v1_missing_field"
    if data["assessment"] is None:
        return "derived_from_schema_v1_null"
    return "validated_schema_v1_extension"
