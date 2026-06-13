from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from qiskit_qkd.analysis import (
    summarize_metric_rows,
    sweep_bb84_time,
    sweep_scenario_parameter,
)
from qiskit_qkd.channels import channel_state_from_scenario
from qiskit_qkd.config import (
    ChannelConfig,
    DecoyIntensity,
    E91Config,
    EveConfig,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.config.dynamics import validate_parameter_target
from qiskit_qkd.detectors import detector_state_from_scenario
from qiskit_qkd.protocols import BB84Protocol, E91Protocol
from qiskit_qkd.sources import source_state_from_scenario
from qiskit_qkd.temporal import ParameterResolver
from qiskit_qkd.timing import timing_state_from_scenario

from .errors import ApiValidationError, api_validation_error


def scenario_from_body(body: Mapping[str, Any]) -> Scenario:
    scenario_data = body.get("scenario", body)
    if not isinstance(scenario_data, Mapping):
        raise ApiValidationError(
            [{"loc": "scenario", "msg": "scenario must be an object"}],
        )
    try:
        return Scenario.from_dict(scenario_data)
    except (TypeError, ValueError) as exc:
        raise api_validation_error(exc, payload=scenario_data) from exc


def run_scenario_job(scenario_data: Mapping[str, Any]) -> dict[str, Any]:
    scenario = Scenario.from_dict(scenario_data)
    scenario = _cap_event_sample(ParameterResolver().scenario_at(scenario, time_s=0.0))
    protocol = _protocol_for(scenario)
    result = protocol.run(scenario)
    return {
        "result_summary": result.summary(),
        "result": _result_payload(result.to_dict()),
    }


def sweep_scenario_job(
    scenario_data: Mapping[str, Any],
    axis: Mapping[str, Any],
    series: Mapping[str, Any] | None,
    repeats: int,
) -> dict[str, Any]:
    scenario = Scenario.from_dict(scenario_data)
    protocol = _protocol_for(scenario)
    time_axis = bool(axis.get("time_axis") or axis.get("target") == "time_s")
    axis_values = parse_axis_values(axis["values"])
    if time_axis and isinstance(protocol, BB84Protocol):
        rows = sweep_bb84_time(
            protocol,
            scenario,
            axis_values,
            repeats=repeats,
        )
        return {
            "rows": rows,
            "summary": summarize_metric_rows(
                rows,
                group_by=("time_s",),
                metrics=("qber", "secret_key_rate_bps", "gain", "detected"),
            ),
        }
    axis_target = validate_parameter_target(str(axis["target"]))
    group_by = [axis_target]
    all_rows: list[dict[str, Any]] = []
    if series is None:
        all_rows.extend(
            sweep_scenario_parameter(
                protocol,
                scenario,
                axis_target,
                axis_values,
                repeats=repeats,
            ),
        )
    else:
        series_target = validate_parameter_target(str(series["target"]))
        group_by.append(series_target)
        for series_value in parse_axis_values(series["values"]):
            series_scenario = set_target(scenario, series_target, series_value)
            rows = sweep_scenario_parameter(
                protocol,
                series_scenario,
                axis_target,
                axis_values,
                repeats=repeats,
            )
            for row in rows:
                row[series_target] = series_value
            all_rows.extend(rows)
    return {
        "rows": all_rows,
        "summary": summarize_metric_rows(
            all_rows,
            group_by=tuple(group_by),
            metrics=("qber", "secret_key_rate_bps", "gain", "detected"),
        ),
    }


def characterize_section(
    section: str,
    body: Mapping[str, Any],
) -> dict[str, Any]:
    scenario = scenario_from_body(body)
    axis = body.get("axis")
    if axis is None:
        return {"section": section, "state": _state_for(section, scenario)}
    if not isinstance(axis, Mapping):
        raise ApiValidationError([{"loc": "axis", "msg": "axis must be an object"}])
    target = validate_parameter_target(str(axis["target"]))
    rows = []
    for value in parse_axis_values(axis["values"]):
        effective = set_target(scenario, target, value)
        row = _state_for(section, effective)
        row[target] = value
        rows.append(row)
    return {"section": section, "rows": rows}


def dynamics_preview(body: Mapping[str, Any]) -> dict[str, Any]:
    scenario = scenario_from_body(body)
    resolver = ParameterResolver()
    raw_points = body.get("time_points_s")
    if raw_points is None:
        raw_points = [0.0, scenario.duration_s / 2.0, scenario.duration_s]
    rows = []
    for time_s in raw_points:
        time = float(time_s)
        row = {"time_s": time}
        row.update(resolver.parameter_values(scenario, time_s=time))
        rows.append(row)
    return {"rows": rows}


def import_experiment_payload(body: Mapping[str, Any]) -> dict[str, Any]:
    if "experiment" in body and isinstance(body["experiment"], Mapping):
        return dict(body["experiment"])
    return dict(body)


def presets_payload() -> dict[str, Any]:
    presets = [
        (
            "Fibra metropolitana",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=7,
                channel=ChannelConfig(kind="fiber", distance_km=25.0),
            ),
        ),
        (
            "Satélite LEO",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=8,
                channel=ChannelConfig(
                    kind="space",
                    distance_km=500.0,
                    beam_divergence_rad=2e-6,
                ),
            ),
        ),
        (
            "PNS sobre decoy débil",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=9,
                source=SourceConfig(
                    kind="decoy_weak_coherent",
                    decoy_intensities=(
                        DecoyIntensity("signal", 0.5, 0.8),
                        DecoyIntensity("decoy", 0.1, 0.15),
                        DecoyIntensity("vacuum", 0.0, 0.05),
                    ),
                ),
                eavesdropper=EveConfig(kind="pns", pns_split_probability=0.5),
            ),
        ),
        (
            "E91 con scintillation",
            Scenario(
                pulses=1024,
                clock_rate_hz=1_000_000.0,
                seed=91,
                protocol=ProtocolConfig(name="e91"),
                source=SourceConfig(kind="entangled_pair"),
                e91=E91Config(),
                channel=ChannelConfig(kind="space", scintillation_sigma=0.2),
                post_processing=PostProcessingConfig(qber_abort_threshold=None),
            ),
        ),
    ]
    return {
        "presets": [
            {"name": name, "scenario": scenario.to_dict(), "digest": scenario.digest()}
            for name, scenario in presets
        ],
    }


def parse_axis_values(values: Any) -> list[float | int | bool | None]:
    if isinstance(values, list):
        return values
    if not isinstance(values, Mapping):
        raise ApiValidationError(
            [{"loc": "values", "msg": "values must be a list or range"}],
        )
    start = float(values["start"])
    stop = float(values["stop"])
    steps = int(values["steps"])
    if steps < 1:
        raise ApiValidationError(
            [{"loc": "values.steps", "msg": "steps must be positive"}],
        )
    if steps == 1:
        return [start]
    if values.get("scale") == "log":
        if start <= 0.0 or stop <= 0.0:
            raise ApiValidationError(
                [{"loc": "values", "msg": "log ranges require positive bounds"}],
            )
        ratio = (math.log10(stop) - math.log10(start)) / (steps - 1)
        return [10 ** (math.log10(start) + index * ratio) for index in range(steps)]
    delta = (stop - start) / (steps - 1)
    return [start + index * delta for index in range(steps)]


def set_target(scenario: Scenario, target: str, value: Any) -> Scenario:
    section, field = validate_parameter_target(target).split(".")
    if section == "scenario":
        return replace(scenario, **{field: value})
    section_config = getattr(scenario, section)
    return replace(scenario, **{section: replace(section_config, **{field: value})})


def _state_for(section: str, scenario: Scenario) -> dict[str, Any]:
    if section == "source":
        return source_state_from_scenario(scenario).to_dict()
    if section == "channel":
        return channel_state_from_scenario(scenario).to_dict()
    if section == "detector":
        return detector_state_from_scenario(scenario).to_dict()
    if section == "timing":
        return timing_state_from_scenario(scenario).to_dict()
    raise ApiValidationError(
        [{"loc": "section", "msg": f"unknown section {section!r}"}],
    )


def _protocol_for(scenario: Scenario) -> BB84Protocol | E91Protocol:
    if scenario.protocol.name == "e91":
        return E91Protocol()
    return BB84Protocol()


def _cap_event_sample(scenario: Scenario) -> Scenario:
    if scenario.event_sample_size <= 200:
        return scenario
    return replace(scenario, event_sample_size=200)


def _result_payload(result: dict[str, Any]) -> dict[str, Any]:
    sample = result.get("event_sample")
    if isinstance(sample, list) and len(sample) > 200:
        result = dict(result)
        result["event_sample"] = sample[:200]
    return result
