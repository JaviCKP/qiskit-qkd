from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from panel.api.app import create_app
from panel.api.runtime import MAX_SWEEP_EVALUATIONS, validate_sweep_request
from qiskit_qkd.analysis import expand_compact_sweep_rows
from qiskit_qkd.config import (
    ChannelConfig,
    DecoyIntensity,
    DynamicConfig,
    ParameterSchedule,
    ProtocolConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.temporal import ConstantProfile, LinearRampProfile


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(store_dir=tmp_path, use_processes=False))


def _scenario(**updates: object) -> dict[str, object]:
    values = {"pulses": 8, "clock_rate_hz": 1_000_000.0, "seed": 7}
    values.update(updates)
    return Scenario(**values).to_dict()


def _decoy_source() -> SourceConfig:
    return SourceConfig(
        kind="decoy_weak_coherent",
        mean_photon_number=0.7,
        decoy_intensities=(
            DecoyIntensity("signal", 0.5, 0.8),
            DecoyIntensity("decoy", 0.1, 0.15),
            DecoyIntensity("vacuum", 0.0, 0.05),
        ),
    )


def _linear_dynamic() -> DynamicConfig:
    return DynamicConfig(
        parameter_schedules=(
            ParameterSchedule(
                target="channel.distance_km",
                profile=LinearRampProfile(
                    start_s=0.0,
                    end_s=1.0,
                    start_value=0.0,
                    end_value=10.0,
                ),
            ),
        ),
    )


def test_validate_returns_additive_capability_warnings(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/scenarios/validate",
        json={"scenario": _scenario(source=_decoy_source())},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["warnings"][0]["code"] == (
        "SOURCE_MEAN_PHOTON_NUMBER_SHADOWED"
    )
    assert response.json()["warnings"][0]["loc"] == "source.mean_photon_number"


def test_validate_keeps_an_ideal_neutral_preset_warning_free(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/scenarios/validate",
        json={
            "scenario": _scenario(
                source=SourceConfig(kind="ideal", decoy_intensities=()),
                channel=ChannelConfig(kind="ideal", attenuation_db_km=0.0),
            ),
        },
    )

    assert response.status_code == 200
    assert response.json()["warnings"] == []


def test_validate_rejects_protocol_source_mismatch_with_structured_issue(
    tmp_path: Path,
) -> None:
    response = _client(tmp_path).post(
        "/api/scenarios/validate",
        json={"scenario": _scenario(protocol=ProtocolConfig(name="e91"))},
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "E91_SOURCE_REQUIRED"
    assert issue["loc"] == "source.kind"
    assert issue["severity"] == "error"
    assert issue["suggestion"]


def test_sweep_preflight_rejects_shadowed_scalar_target(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(source=_decoy_source()),
            "axis": {"target": "source.mean_photon_number", "values": [0.1, 0.5]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "TARGET_HAS_NO_EFFECT"


@pytest.mark.parametrize(
    "dynamic",
    [
        DynamicConfig(),
        DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.distance_km",
                    profile=ConstantProfile(start_s=0.0, end_s=1.0, value=5.0),
                ),
            ),
        ),
    ],
)
def test_time_sweep_preflight_rejects_missing_effective_evolution(
    tmp_path: Path,
    dynamic: DynamicConfig,
) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(dynamic=dynamic),
            "axis": {"target": "time_s", "values": [0.0, 0.5, 1.0]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "TIME_EVOLUTION_REQUIRED"


def test_time_sweep_rejects_series_before_enqueuing(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(dynamic=_linear_dynamic()),
            "axis": {"target": "time_s", "values": [0.0, 1.0]},
            "series": {"target": "detector.efficiency", "values": [0.5, 1.0]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "TIME_SERIES_UNSUPPORTED"


def test_time_sweep_rejects_e91_before_enqueuing(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(
                protocol=ProtocolConfig(name="e91"),
                source=SourceConfig(kind="entangled_pair"),
                dynamic=_linear_dynamic(),
            ),
            "axis": {"target": "time_s", "values": [0.0, 1.0]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == ("TIME_SWEEP_UNSUPPORTED_PROTOCOL")


def test_time_sweep_rows_preserve_paired_seeds_and_resolution_provenance(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    scenario_payload = _scenario(
        channel=ChannelConfig(kind="fiber"),
        dynamic=_linear_dynamic(),
    )

    created = client.post(
        "/api/sweeps",
        json={
            "scenario": scenario_payload,
            "axis": {"target": "time_s", "values": [0.0, 1.0]},
            "repeats": 2,
        },
    )

    assert created.status_code == 200
    job_id = created.json()["job_id"]
    payload = client.get(f"/api/sweeps/{job_id}").json()
    assert "result" not in payload
    result = client.get(f"/api/sweeps/{job_id}/result").json()
    assert result["schema_version"] == 2
    assert result["row_encoding"] == "scalar-records-v1"
    assert all(
        "provenance" not in row and "effective_model" not in row
        for row in result["rows"]
    )
    rows = expand_compact_sweep_rows(result)
    requested_digest = Scenario.from_dict(scenario_payload).digest()
    assert [row["seed"] for row in rows] == [7, 8, 7, 8]
    assert [row["resolution_time_s"] for row in rows] == [0.0, 0.0, 1.0, 1.0]
    for row in rows:
        assert row["requested_scenario_digest"] == requested_digest
        assert row["effective_scenario_digest"] != requested_digest
        assert row["provenance"]["requested_scenario_digest"] == requested_digest
        assert (
            row["provenance"]["effective_scenario_digest"]
            == (row["effective_scenario_digest"])
        )
        assert row["provenance"]["resolution_time_s"] == row["time_s"]
        effective_model = row["provenance"]["effective_model"]
        assert (
            effective_model["effective_values"]["channel.distance_km"]
            == (row["channel.distance_km"])
        )
        assert "channel_loss_db" in effective_model["derived_parameters"]
        assert isinstance(row["qber_defined"], bool)
        if not row["qber_defined"]:
            assert row["qber"] is None


def test_sweep_rejects_identical_axis_and_series_targets(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {"target": "channel.distance_km", "values": [0.0, 1.0]},
            "series": {"target": "channel.distance_km", "values": [2.0, 3.0]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "AXIS_SERIES_TARGET_CONFLICT"


def test_catalog_exposes_capabilities_without_secure_metric(tmp_path: Path) -> None:
    payload = _client(tmp_path).get("/api/catalog").json()

    assert "capabilities" in payload
    assert "source.mean_photon_number" in payload["capabilities"]["parameters"]
    sections = {section["key"] for section in payload["sections"]}
    assert sections >= {"post_processing", "eavesdropper", "e91", "dynamic"}
    field_keys = {
        field["key"] for section in payload["sections"] for field in section["fields"]
    }
    assert "scenario.store_full_event_log" in field_keys
    assert "dynamic.parameter_schedules" in field_keys
    metric_keys = {metric["key"] for metric in payload["metrics"]}
    assert "secure" not in metric_keys
    metrics = {metric["key"]: metric for metric in payload["metrics"]}
    assert metrics["abort"]["label_es"] == "umbral agregado (legacy)"
    assert metrics["abort"]["scope"] == (
        "legacy aggregate threshold flag; not security/key/verification"
    )
    assert metrics["secret_key_rate_bps"]["unit"] == "bit/s"
    assert payload["capabilities"]["metrics"]["secret_key_rate_bps"]["scope"]


def test_catalog_does_not_claim_signed_parameters_are_non_negative(
    tmp_path: Path,
) -> None:
    payload = _client(tmp_path).get("/api/catalog").json()
    fields = {
        field["key"]: field
        for section in payload["sections"]
        for field in section["fields"]
    }

    for target in (
        "timing.clock_offset_s",
        "channel.chromatic_dispersion_ps_nm_km",
    ):
        assert fields[target]["min"] is None
        assert fields[target]["scale"] == "linear"


def test_integer_pulse_range_is_normalized_for_guided_sweeps() -> None:
    scenario = Scenario(pulses=8, clock_rate_hz=1_000_000.0, seed=7)

    values, series_values = validate_sweep_request(
        scenario,
        {
            "target": "scenario.pulses",
            "values": {"start": 256, "stop": 8192, "steps": 8, "scale": "log"},
        },
        None,
        1,
    )

    assert series_values is None
    assert len(values) == 8
    assert all(isinstance(value, int) and value > 0 for value in values)


def test_explicit_pulse_lists_require_integer_json_values(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {"target": "scenario.pulses", "values": [8.0]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == ("TARGET_VALUE_REQUIRES_INTEGER")


def test_time_axis_flag_cannot_override_a_different_target(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(dynamic=_linear_dynamic()),
            "axis": {
                "target": "channel.distance_km",
                "time_axis": True,
                "values": [0.0, 1.0],
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "TIME_AXIS_TARGET_CONFLICT"


def test_time_axis_flag_requires_an_actual_boolean(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {
                "target": "channel.distance_km",
                "time_axis": "false",
                "values": [0.0, 1.0],
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "TIME_AXIS_FLAG_INVALID"


def test_two_dimensional_preflight_rejects_an_inactive_series_slice(
    tmp_path: Path,
) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(
                channel=ChannelConfig(kind="fiber", distance_km=1.0),
            ),
            "axis": {
                "target": "channel.attenuation_db_km",
                "values": [0.1, 0.3],
            },
            "series": {
                "target": "channel.distance_km",
                "values": [0.0, 1.0],
            },
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "TARGET_HAS_NO_EFFECT"
    assert issue["loc"] == "channel.attenuation_db_km"


def test_two_dimensional_preflight_uses_each_series_scenario() -> None:
    scenario = Scenario(
        pulses=8,
        clock_rate_hz=1_000_000.0,
        seed=7,
        channel=ChannelConfig(kind="fiber", distance_km=0.0),
    )

    axis_values, series_values = validate_sweep_request(
        scenario,
        {"target": "channel.attenuation_db_km", "values": [0.1, 0.3]},
        {"target": "channel.distance_km", "values": [1.0, 2.0]},
        1,
    )

    assert axis_values == [0.1, 0.3]
    assert series_values == [1.0, 2.0]


@pytest.mark.parametrize(
    ("target", "expected_code"),
    [
        ("channel.attenuation_db_km", "TARGET_HAS_NO_EFFECT"),
        ("unknown.target", "TARGET_NOT_SUPPORTED"),
    ],
)
def test_characterize_rejects_ineffective_targets_with_structured_422(
    tmp_path: Path,
    target: str,
    expected_code: str,
) -> None:
    response = _client(tmp_path).post(
        "/api/characterize/channel",
        json={
            "scenario": _scenario(),
            "axis": {"target": target, "values": [0.1, 0.9]},
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == expected_code


def test_characterize_applies_the_effective_axis_target(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/characterize/channel",
        json={
            "scenario": _scenario(
                channel=ChannelConfig(kind="fiber", distance_km=10.0),
            ),
            "axis": {
                "target": "channel.attenuation_db_km",
                "values": [0.1, 0.9],
            },
        },
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert [row["channel.attenuation_db_km"] for row in rows] == [0.1, 0.9]
    assert rows[0]["transmittance"] > rows[1]["transmittance"]


@pytest.mark.parametrize("time_point", [-1.0, False, "1.0"])
def test_dynamics_preview_rejects_invalid_time_points_with_422(
    tmp_path: Path,
    time_point: object,
) -> None:
    response = _client(tmp_path).post(
        "/api/dynamics/preview",
        json={"scenario": _scenario(), "time_points_s": [time_point]},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == "time_points_s.0"


@pytest.mark.parametrize("repeats", [True, 1.0, 1.5, "2"])
def test_sweep_repeats_are_strict_positive_integers(
    tmp_path: Path,
    repeats: object,
) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {"target": "scenario.pulses", "values": [8]},
            "repeats": repeats,
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "SWEEP_REPEATS_INVALID"
    assert issue["loc"] == "repeats"
    assert issue["suggestion"]


@pytest.mark.parametrize("steps", [True, 2.0, 2.5, 0])
def test_range_steps_are_strict_positive_integers(
    tmp_path: Path,
    steps: object,
) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {
                "target": "scenario.pulses",
                "values": {"start": 8, "stop": 16, "steps": steps},
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["loc"] == "axis.values.steps"


def test_sweep_size_limit_counts_axis_series_and_repeats(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {"target": "detector.efficiency", "values": [0.5] * 65},
            "series": {
                "target": "detector.dark_count_rate_hz",
                "values": [0.0] * 64,
            },
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "SWEEP_SIZE_EXCEEDED"
    assert issue["value"] == 65 * 64
    assert issue["context"]["max_evaluations"] == MAX_SWEEP_EVALUATIONS
    assert str(MAX_SWEEP_EVALUATIONS) in issue["suggestion"]


def test_sweep_size_limit_accepts_the_exact_boundary() -> None:
    scenario = Scenario(pulses=8, clock_rate_hz=1_000_000.0, seed=7)

    axis_values, series_values = validate_sweep_request(
        scenario,
        {"target": "detector.efficiency", "values": [0.5] * 64},
        {
            "target": "detector.dark_count_rate_hz",
            "values": [0.0] * 64,
        },
        1,
    )

    assert len(axis_values) * len(series_values or ()) == MAX_SWEEP_EVALUATIONS


def test_range_point_limit_is_rejected_before_materializing_the_axis(
    tmp_path: Path,
) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {
                "target": "scenario.pulses",
                "values": {
                    "start": 8,
                    "stop": 16,
                    "steps": MAX_SWEEP_EVALUATIONS + 1,
                },
            },
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "AXIS_POINT_LIMIT_EXCEEDED"
    assert issue["suggestion"]


def test_characterize_rejects_a_globally_active_but_section_inert_axis(
    tmp_path: Path,
) -> None:
    response = _client(tmp_path).post(
        "/api/characterize/source",
        json={
            "scenario": _scenario(
                channel=ChannelConfig(kind="fiber", distance_km=10.0),
            ),
            "axis": {"target": "channel.distance_km", "values": [1.0, 100.0]},
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "TARGET_HAS_NO_CHARACTERIZATION_EFFECT"
    assert issue["loc"] == "axis.target"


def test_characterize_preserves_cross_section_axes_with_real_effects(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)

    source_response = client.post(
        "/api/characterize/source",
        json={
            "scenario": _scenario(),
            "axis": {"target": "scenario.clock_rate_hz", "values": [1e6, 2e6]},
        },
    )
    detector_response = client.post(
        "/api/characterize/detector",
        json={
            "scenario": _scenario(),
            "axis": {
                "target": "channel.background_count_rate_hz",
                "values": [0.0, 1_000.0],
            },
        },
    )

    assert source_response.status_code == 200
    source_rows = source_response.json()["rows"]
    assert (
        source_rows[0]["mean_photon_rate_hz"] < (source_rows[1]["mean_photon_rate_hz"])
    )
    assert detector_response.status_code == 200
    detector_rows = detector_response.json()["rows"]
    assert (
        detector_rows[0]["p_background_per_gate"]
        < (detector_rows[1]["p_background_per_gate"])
    )


@pytest.mark.parametrize(
    ("axis", "series", "expected_loc"),
    [
        (
            {"target": "scenario.pulses", "values": [8], "typo": True},
            None,
            "axis.typo",
        ),
        (
            {"target": "scenario.pulses", "values": [8]},
            {
                "target": "scenario.clock_rate_hz",
                "values": [1_000_000.0],
                "time_axis": False,
            },
            "series.time_axis",
        ),
        (
            {
                "target": "scenario.pulses",
                "values": {
                    "start": 8,
                    "stop": 16,
                    "steps": 2,
                    "scales": "log",
                },
            },
            None,
            "axis.values.scales",
        ),
    ],
)
def test_sweep_rejects_unknown_axis_series_and_range_fields(
    tmp_path: Path,
    axis: dict[str, object],
    series: dict[str, object] | None,
    expected_loc: str,
) -> None:
    body: dict[str, object] = {"scenario": _scenario(), "axis": axis}
    if series is not None:
        body["series"] = series

    response = _client(tmp_path).post("/api/sweeps", json=body)

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "UNKNOWN_REQUEST_FIELD"
    assert issue["loc"] == expected_loc
    assert issue["suggestion"]


@pytest.mark.parametrize(
    "values",
    [
        [8, 8],
        {"start": 1, "stop": 2, "steps": 4},
    ],
)
def test_pulse_sweeps_reject_points_that_collide_after_integer_normalization(
    tmp_path: Path,
    values: object,
) -> None:
    response = _client(tmp_path).post(
        "/api/sweeps",
        json={
            "scenario": _scenario(),
            "axis": {"target": "scenario.pulses", "values": values},
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "TARGET_VALUES_COLLIDE"
    assert issue["suggestion"]


def test_characterize_caps_explicit_axis_lists(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/characterize/source",
        json={
            "scenario": _scenario(),
            "axis": {
                "target": "scenario.clock_rate_hz",
                "values": [1_000_000.0] * (MAX_SWEEP_EVALUATIONS + 1),
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "AXIS_POINT_LIMIT_EXCEEDED"


def test_dynamics_preview_caps_explicit_time_lists(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/dynamics/preview",
        json={
            "scenario": _scenario(),
            "time_points_s": [0.0] * (MAX_SWEEP_EVALUATIONS + 1),
        },
    )

    assert response.status_code == 422
    issue = response.json()["errors"][0]
    assert issue["code"] == "TIME_POINT_LIMIT_EXCEEDED"
    assert issue["suggestion"]
