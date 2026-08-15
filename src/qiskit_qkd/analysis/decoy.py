"""Plot-ready helpers for decoy-state simulation outputs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qiskit_qkd.results import SimulationResult

DecoyRowValue = str | int | float | bool | None
DecoyRow = dict[str, DecoyRowValue]


def decoy_rows_from_result(result: SimulationResult) -> list[DecoyRow]:
    """Return flat, JSON-safe decoy rows suitable for CSV, Pandas, or plots."""

    rows: list[DecoyRow] = []
    for intensity_class in sorted(name for name in result.decoy if name != "security"):
        row = result.decoy[intensity_class]
        if isinstance(row, Mapping):
            rows.append(
                _flatten_row(
                    row_type="intensity",
                    intensity_class=intensity_class,
                    values=row,
                ),
            )

    security = result.decoy.get("security")
    if isinstance(security, Mapping):
        rows.append(
            _flatten_row(
                row_type="security",
                intensity_class=None,
                values=security,
            ),
        )
    return rows


def _flatten_row(
    *,
    row_type: str,
    intensity_class: str | None,
    values: Mapping[str, Any],
) -> DecoyRow:
    output: DecoyRow = {
        "row_type": row_type,
        "intensity_class": intensity_class,
    }
    for key, value in values.items():
        output[key] = _flat_value(value)
    return output


def _flat_value(value: Any) -> DecoyRowValue:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple):
        return "; ".join(str(item) for item in value)
    return str(value)
