"""Plot-ready helpers for Bell-test simulation outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qiskit_qkd.results import SimulationResult

BellRowValue = str | int | float | bool | None
BellRow = dict[str, BellRowValue]


def bell_rows_from_result(result: SimulationResult) -> list[BellRow]:
    """Return flat E91 setting rows suitable for CSV, Pandas, or plots."""

    rows = result.bell.get("setting_rows", [])
    if not isinstance(rows, list):
        return []
    return [
        _flatten_row(row)
        for row in rows
        if isinstance(row, Mapping)
    ]


def _flatten_row(values: Mapping[str, Any]) -> BellRow:
    output: BellRow = {}
    for key, value in values.items():
        output[key] = _flat_value(value)
    return output


def _flat_value(value: Any) -> BellRowValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
