"""Analysis helpers for QKD simulation outputs."""

from qiskit_qkd.config.dynamics import SWEEPABLE_TARGETS

from .bell import BellRow, BellRowValue, bell_rows_from_result
from .decoy import DecoyRow, DecoyRowValue, decoy_rows_from_result
from .metrics import (
    MetricRow,
    MetricRowValue,
    add_derived_metrics,
    chsh_margin,
    metric_rows_from_results,
    qber_margin,
    secure_distance_limit,
    summarize_metric_rows,
)
from .sweeps import (
    COMPACT_SWEEP_SCHEMA_VERSION,
    compact_sweep_payload,
    expand_compact_sweep_rows,
    expand_compact_sweep_summary,
    sweep_bb84_distance,
    sweep_bb84_time,
    sweep_scenario_parameter,
)

__all__ = [
    "BellRow",
    "BellRowValue",
    "DecoyRow",
    "DecoyRowValue",
    "MetricRow",
    "MetricRowValue",
    "add_derived_metrics",
    "bell_rows_from_result",
    "chsh_margin",
    "COMPACT_SWEEP_SCHEMA_VERSION",
    "compact_sweep_payload",
    "decoy_rows_from_result",
    "expand_compact_sweep_rows",
    "expand_compact_sweep_summary",
    "metric_rows_from_results",
    "qber_margin",
    "secure_distance_limit",
    "summarize_metric_rows",
    "SWEEPABLE_TARGETS",
    "sweep_bb84_distance",
    "sweep_bb84_time",
    "sweep_scenario_parameter",
]
