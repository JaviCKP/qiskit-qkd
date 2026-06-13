from __future__ import annotations

from qiskit_qkd.config import Scenario
from qiskit_qkd.config.dynamics import SWEEPABLE_TARGETS
from qiskit_qkd.results import Metrics


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
    return {
        "sections": sections,
        "metrics": [
            {"key": key, "label_es": key.replace("_", " "), "unit": _metric_unit(key)}
            for key in Metrics(pulses=0).to_dict()
        ]
        + [
            {"key": "secure", "label_es": "seguro", "unit": None},
            {"key": "qber_margin", "label_es": "margen QBER", "unit": None},
            {"key": "chsh_margin", "label_es": "margen CHSH", "unit": None},
        ],
    }


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
) -> dict[str, object]:
    return {
        "key": key,
        "section": key.split(".", 1)[0],
        "label_es": label,
        "type": kind,
        "unit": unit,
        "default": default,
        "help_es": label,
        "sweepable": key in SWEEPABLE_TARGETS,
    }


def _metric_unit(key: str) -> str | None:
    if key.endswith("_bps") or key.endswith("_rate_hz"):
        return "Hz"
    if key.endswith("_db"):
        return "dB"
    return None


def _complete_sections(sections: list[dict[str, object]]) -> None:
    default = Scenario(pulses=1024, clock_rate_hz=1_000_000.0, seed=7).to_dict()
    by_key = {section["key"]: section for section in sections}
    for section_key, section_value in default.items():
        if section_key == "schema_version":
            continue
        section = by_key.setdefault(
            section_key,
            _section(section_key, section_key.replace("_", " ").title(), []),
        )
        fields = section["fields"]
        assert isinstance(fields, list)
        existing = {field["key"] for field in fields}
        if isinstance(section_value, dict):
            for field_key, default_value in section_value.items():
                key = f"{section_key}.{field_key}"
                if key not in existing:
                    fields.append(
                        _field(
                            key,
                            field_key.replace("_", " "),
                            _field_type(default_value),
                            default=default_value,
                        ),
                    )
        elif section_key not in {"dynamic", "metadata"}:
            key = f"scenario.{section_key}"
            if key not in existing:
                fields.append(
                    _field(
                        key,
                        section_key.replace("_", " "),
                        _field_type(section_value),
                        default=section_value,
                    ),
                )


def _field_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    return "text"
