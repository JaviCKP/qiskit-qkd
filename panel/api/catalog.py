from __future__ import annotations

from qiskit_qkd.config import Scenario
from qiskit_qkd.config.capabilities import (
    capability_registry_payload,
    metric_capability_payload,
    parameter_capability_payload,
)
from qiskit_qkd.config.domain_metadata import (
    domain_fields_payload,
    domain_metadata_payload,
)
from qiskit_qkd.config.schema import (
    CHANNEL_KINDS,
    DECOY_SECURITY_METHODS,
    DETECTOR_KINDS,
    E91_BELL_STATES,
    PROTOCOL_NAMES,
    SLOT_ASSIGNMENT_POLICIES,
    SOURCE_KINDS,
)
from qiskit_qkd.results import Metrics

_SIGNED_PARAMETER_LIMITS: dict[str, dict[str, object]] = {
    "timing.clock_offset_s": {"step": 1e-9, "scale": "linear"},
    "channel.chromatic_dispersion_ps_nm_km": {
        "step": 0.1,
        "scale": "linear",
    },
}

_DOMAIN_FIELDS = {
    field["key"]: field for field in domain_fields_payload()
}


def catalog_payload() -> dict[str, object]:
    sections = [
        _section(
            "scenario",
            "Escenario",
            [
                _field("scenario.pulses", "Pulsos", "integer", default=1024),
                _field(
                    "scenario.clock_rate_hz",
                    "Reloj",
                    "number",
                    unit="Hz",
                    default=1_000_000.0,
                ),
                _field("scenario.seed", "Seed", "integer", default=7),
                _field(
                    "scenario.event_sample_size",
                    "Muestra de eventos",
                    "integer",
                    default=200,
                ),
            ],
        ),
        _section(
            "protocol",
            "Protocolo",
            [
                _field("protocol.name", "Protocolo", "select", default="bb84"),
                _field(
                    "protocol.basis_choices",
                    "Bases BB84",
                    "string_list",
                    default=["Z", "X"],
                ),
            ],
        ),
        _section(
            "source",
            "Fuente",
            [
                _field(
                    "source.kind",
                    "Tipo",
                    "select",
                    default="ideal_single_photon",
                ),
                _field(
                    "source.emission_probability",
                    "Probabilidad de emision",
                    "number",
                    default=1.0,
                ),
                _field(
                    "source.mean_photon_number",
                    "Fotones medios",
                    "number",
                    default=None,
                ),
                _field(
                    "source.preparation_error_probability",
                    "Error de preparacion",
                    "number",
                    default=0.0,
                ),
                _field("source.decoy_intensities", "Intensidades decoy", "table"),
            ],
        ),
        _section(
            "channel",
            "Canal",
            [
                _field("channel.kind", "Familia", "select", default="ideal"),
                _field(
                    "channel.distance_km",
                    "Distancia",
                    "number",
                    unit="km",
                    default=0.0,
                ),
                _field(
                    "channel.attenuation_db_km",
                    "Atenuacion",
                    "number",
                    unit="dB/km",
                    default=0.2,
                ),
                _field(
                    "channel.fixed_loss_db",
                    "Perdida fija",
                    "number",
                    unit="dB",
                    default=0.0,
                ),
                _field(
                    "channel.depolarizing_probability",
                    "Despolarizacion",
                    "number",
                    default=0.0,
                ),
                _field(
                    "channel.background_count_rate_hz",
                    "Fondo",
                    "number",
                    unit="Hz",
                    default=0.0,
                ),
            ],
        ),
        _section(
            "detector",
            "Detector",
            [
                _field("detector.kind", "Tipo", "select", default="ideal"),
                _field("detector.efficiency", "Eficiencia", "number", default=1.0),
                _field(
                    "detector.dark_count_rate_hz",
                    "Dark counts",
                    "number",
                    unit="Hz",
                    default=0.0,
                ),
                _field(
                    "detector.gate_width_s",
                    "Ancho de gate",
                    "number",
                    unit="s",
                    default=1e-9,
                ),
                _field(
                    "detector.dead_time_s",
                    "Tiempo muerto",
                    "number",
                    unit="s",
                    default=0.0,
                ),
                _field(
                    "detector.afterpulse_probability",
                    "Afterpulse",
                    "number",
                    default=0.0,
                ),
                _field(
                    "detector.readout_error_probability",
                    "Error de lectura",
                    "number",
                    default=0.0,
                ),
                _field(
                    "detector.double_click_policy",
                    "Doble click",
                    "select",
                    default="discard",
                ),
            ],
        ),
        _section(
            "timing",
            "Timing",
            [
                _field(
                    "timing.propagation_delay_s",
                    "Retardo",
                    "number",
                    unit="s",
                    default=0.0,
                ),
                _field(
                    "timing.jitter_std_s",
                    "Jitter",
                    "number",
                    unit="s",
                    default=0.0,
                ),
                _field(
                    "timing.clock_offset_s",
                    "Offset de reloj",
                    "number",
                    unit="s",
                    default=0.0,
                ),
                _field(
                    "timing.clock_drift_ppm",
                    "Drift",
                    "number",
                    unit="ppm",
                    default=0.0,
                ),
            ],
        ),
    ]
    _complete_sections(sections)
    metric_keys = tuple(Metrics(pulses=0).to_dict()) + (
        "qber_margin",
        "chsh_margin",
    )
    payload: dict[str, object] = {
        "sections": sections,
        "metrics": [
            {
                "key": key,
                "label_es": _metric_label(key),
                "unit": _metric_unit(key),
                **metric_capability_payload(key),
            }
            for key in metric_keys
        ],
        "capabilities": capability_registry_payload(),
    }
    # Additive metadata contract.  Existing sections/capabilities remain
    # stable for legacy clients while new clients can consume one source of
    # truth for defaults, units, conditions, and scientific media.
    payload.update(domain_metadata_payload())
    return payload


def _section(
    key: str,
    label: str,
    fields: list[dict[str, object]],
) -> dict[str, object]:
    return {"key": key, "label_es": label, "fields": fields}


def _field(
    key: str,
    label: str,
    kind: str,
    *,
    unit: str | None = None,
    default: object = None,
    options: list[str] | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
    scale: str = "linear",
    visible_when: dict[str, object] | None = None,
) -> dict[str, object]:
    domain = _DOMAIN_FIELDS.get(key, {})
    resolved_unit = domain.get("unit", unit)
    resolved_default = domain.get("default", default)
    resolved_options = domain.get("options", options)
    resolved_visible_when = domain.get("visible_when", visible_when)
    limits = _limits_for(key)
    capability = parameter_capability_payload(key)
    return {
        "key": key,
        "section": key.split(".", 1)[0],
        "label_es": label,
        "type": kind,
        "unit": resolved_unit,
        "default": resolved_default,
        "min": minimum if minimum is not None else limits.get("min"),
        "max": maximum if maximum is not None else limits.get("max"),
        "step": step if step is not None else limits.get("step"),
        "scale": scale if scale != "linear" else limits.get("scale", "linear"),
        "options": (
            resolved_options
            if resolved_options is not None
            else _options_for(key)
        ),
        "visible_when": (
            resolved_visible_when
            if resolved_visible_when is not None
            else _visible_when_for(key)
        ),
        "help_es": label,
        "sweepable": bool(capability.get("sweepable", False)),
        **capability,
    }


def _metric_label(key: str) -> str:
    labels = {
        "abort": "umbral agregado (legacy)",
        "secret_key_rate_bps": "tasa de clave estimada",
        "chsh_s": "CHSH observado",
        "qber_margin": "margen QBER",
        "chsh_margin": "margen CHSH",
    }
    return labels.get(key, key.replace("_", " "))


def _metric_unit(key: str) -> str | None:
    if key.endswith("_bps"):
        return "bit/s"
    if key.endswith("_rate_hz"):
        return "Hz"
    if key.endswith("_db"):
        return "dB"
    return None


def _complete_sections(sections: list[dict[str, object]]) -> None:
    default = Scenario(pulses=1024, clock_rate_hz=1_000_000.0, seed=7).to_dict()
    by_key = {section["key"]: section for section in sections}
    for section_key, section_value in default.items():
        if section_key in {"schema_version", "metadata"}:
            continue
        if isinstance(section_value, dict):
            section = by_key.get(section_key)
            if section is None:
                section = _section(
                    section_key,
                    section_key.replace("_", " ").title(),
                    [],
                )
                by_key[section_key] = section
                sections.append(section)
            fields = section["fields"]
            assert isinstance(fields, list)
            existing = {field["key"] for field in fields}
            for field_key, default_value in section_value.items():
                key = f"{section_key}.{field_key}"
                if key not in existing:
                    fields.append(
                        _field_for_default(key, field_key, default_value),
                    )
        else:
            section = by_key["scenario"]
            fields = section["fields"]
            assert isinstance(fields, list)
            existing = {field["key"] for field in fields}
            key = f"scenario.{section_key}"
            if key not in existing:
                fields.append(
                    _field_for_default(key, section_key, section_value),
                )


def _field_for_default(
    key: str,
    field_key: str,
    default_value: object,
) -> dict[str, object]:
    return _field(
        key,
        field_key.replace("_", " "),
        _field_type(default_value, key=key),
        default=default_value,
    )


def _field_type(value: object, *, key: str) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        if key in {"e91.alice_angles_rad", "e91.bob_angles_rad"}:
            return "number_list"
        if key == "protocol.basis_choices":
            return "string_list"
        if key == "dynamic.parameter_schedules":
            return "schedule_list"
        return "json"
    if isinstance(value, dict):
        return "json"
    return "text"


def _options_for(key: str) -> list[str] | None:
    options_by_key = {
        "protocol.name": sorted(PROTOCOL_NAMES),
        "protocol.basis_choices": ["Z", "X"],
        "source.kind": sorted(SOURCE_KINDS),
        "channel.kind": sorted(CHANNEL_KINDS),
        "channel.pdl_axis_basis": ["Z", "X"],
        "detector.kind": sorted(DETECTOR_KINDS),
        "detector.double_click_policy": ["discard", "random", "error"],
        "timing.slot_assignment_policy": sorted(SLOT_ASSIGNMENT_POLICIES),
        "post_processing.decoy_security_method": sorted(DECOY_SECURITY_METHODS),
        "eavesdropper.kind": [
            "none",
            "intercept_resend",
            "photon_number_splitting",
        ],
        "e91.bell_state": sorted(E91_BELL_STATES),
    }
    return options_by_key.get(key)


def _limits_for(key: str) -> dict[str, object]:
    if key in _SIGNED_PARAMETER_LIMITS:
        return dict(_SIGNED_PARAMETER_LIMITS[key])
    if key == "scenario.pulses":
        return {"min": 1, "step": 1, "scale": "log"}
    if key == "scenario.clock_rate_hz":
        return {"min": 1.0, "step": 1.0, "scale": "log"}
    if key in {"scenario.seed", "scenario.event_sample_size"}:
        return {"min": 0, "step": 1}
    if (
        key.endswith("_probability")
        or key.endswith("_fraction")
        or key
        in {
            "detector.efficiency",
            "channel.depolarizing_probability",
            "channel.phase_damping_probability",
        }
    ):
        return {"min": 0.0, "max": 1.0, "step": 0.01}
    if key.endswith("_rate_hz") or key.endswith("_s") or key.endswith("_km"):
        return {"min": 0.0, "step": 0.001, "scale": "log"}
    if key.endswith("_db") or key.endswith("_db_km"):
        return {"min": 0.0, "step": 0.01}
    if key.endswith("_rad") or key.endswith("_ppm"):
        return {"step": 0.001}
    return {}


def _visible_when_for(key: str) -> dict[str, object] | None:
    if key.startswith("e91."):
        return {"target": "protocol.name", "equals": "e91"}
    if key == "source.decoy_intensities":
        return {"target": "source.kind", "equals": "decoy_weak_coherent"}
    if key.startswith("eavesdropper.pns_"):
        return {"target": "eavesdropper.kind", "equals": "photon_number_splitting"}
    if key == "eavesdropper.intercept_probability":
        return {"target": "eavesdropper.kind", "equals": "intercept_resend"}
    if key.startswith("post_processing.decoy_"):
        return {"target": "source.kind", "equals": "decoy_weak_coherent"}
    return None
