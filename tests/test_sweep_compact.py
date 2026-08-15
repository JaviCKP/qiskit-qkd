from __future__ import annotations

import json

import pytest

from qiskit_qkd.analysis import (
    compact_sweep_payload,
    expand_compact_sweep_rows,
    expand_compact_sweep_summary,
)


def _row(index: int, *, seed: int = 100) -> dict[str, object]:
    return {
        "channel.distance_km": float(index),
        "repeat": index % 2,
        "seed": seed + index % 2,
        "qber": 0.01 * index,
        "detected": index + 1,
        "requested_scenario_digest": "request-digest",
        "effective_scenario_digest": f"effective-{index}",
        "assessment": {
            "protocol": "bb84",
            "qber_defined": True,
            "qber_value": 0.01 * index,
            "reason_codes": [],
            "assumptions": ["finite-key"] if index % 2 else ["asymptotic"],
        },
        "provenance": {
            "requested_scenario_digest": "request-digest",
            "effective_scenario_digest": f"effective-{index}",
            "effective_model": {
                "protocol_model": "BB84Protocol",
                "effective_values": {
                    "channel.distance_km": float(index),
                    "channel.attenuation_db_km": 0.2,
                },
                "consumed_parameters": ["channel.distance_km"]
                if index
                else ["channel.attenuation_db_km"],
            },
        },
        "effective_model": {
            "protocol_model": "BB84Protocol",
            "effective_values": {
                "channel.distance_km": float(index),
                "channel.attenuation_db_km": 0.2,
            },
            "consumed_parameters": ["channel.distance_km"]
            if index
            else ["channel.attenuation_db_km"],
        },
    }


def test_compact_rows_factor_metadata_and_expand_without_scientific_loss() -> None:
    rows = [_row(index) for index in range(64)]
    summary = [
        {
            "channel.distance_km": index,
            "qber_mean": index / 100,
            "samples": 2,
            "secure_fraction": index / 64,
        }
        for index in range(64)
    ]
    payload = compact_sweep_payload(
        rows,
        requested_scenario_digest="request-digest",
        summary=summary,
    )

    encoded_rows = json.dumps(rows, separators=(",", ":"))
    encoded_payload = json.dumps(payload, separators=(",", ":"))
    assert len(encoded_payload) < len(encoded_rows) * 0.7
    assert payload["row_encoding"] == "scalar-records-v1"
    assert payload["row_count"] == len(rows)
    assert all(
        not isinstance(value, (dict, list))
        for row in payload["rows"]
        for value in row.values()
    )
    assert expand_compact_sweep_rows(payload) == rows
    assert expand_compact_sweep_summary(payload["summary"]) == summary
    assert any(
        isinstance(column, dict)
        and column.get("encoding") == "dictionary-v1"
        for column in payload["effective_model_columns"].values()
    )


def test_compact_empty_and_single_rows_keep_bounds_and_summary_shape() -> None:
    empty = compact_sweep_payload([])
    assert expand_compact_sweep_rows(empty) == []

    single = compact_sweep_payload([_row(0)], summary=[{"x": 1}])
    assert expand_compact_sweep_rows(single) == [_row(0)]
    assert expand_compact_sweep_summary(single["summary"]) == [{"x": 1}]


def test_compact_rejects_malformed_summary_and_non_json_values() -> None:
    with pytest.raises(TypeError, match="summary must be a list or compact object"):
        expand_compact_sweep_summary("bad")
    with pytest.raises(ValueError, match="finite"):
        compact_sweep_payload([{"x": float("nan")}])
    with pytest.raises(ValueError, match="finite"):
        compact_sweep_payload([{"x": float("inf")}])


def test_compact_rejects_corrupt_counts_and_dictionary_indexes() -> None:
    payload = compact_sweep_payload([_row(0), _row(1)])
    payload["row_count"] = 1
    with pytest.raises(ValueError, match="row_count"):
        expand_compact_sweep_rows(payload)

    payload = compact_sweep_payload([_row(index) for index in range(64)])
    columns = payload["effective_model_columns"]
    encoded = next(value for value in columns.values() if isinstance(value, dict))
    encoded["indexes"][0] = len(encoded["values"])
    with pytest.raises(ValueError, match="out of range"):
        expand_compact_sweep_rows(payload)
