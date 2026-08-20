"""Analysis helpers for QKD simulation outputs."""

from qiskit_qkd.config.dynamics import SWEEPABLE_TARGETS

from .bell import BellRow, BellRowValue, bell_rows_from_result
from .confidence import (
    DEFAULT_CONFIDENCE_LEVEL,
    ConfidenceInterval,
    mean_confidence_interval,
    proportion_confidence_interval,
    t_confidence_interval,
    t_interval,
    wilson_interval,
)
from .decoy import DecoyRow, DecoyRowValue, decoy_rows_from_result
from .metrics import (
    MetricRow,
    MetricRowValue,
    add_derived_metrics,
    authoritative_metrics_from_result,
    authoritative_result_metrics,
    chsh_margin,
    extract_authoritative_metrics,
    metric_rows_from_results,
    observed_metric_rows_from_results,
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
    "ConfidenceInterval",
    "DEFAULT_CONFIDENCE_LEVEL",
    "DecoyRow",
    "DecoyRowValue",
    "MetricRow",
    "MetricRowValue",
    "add_derived_metrics",
    "authoritative_metrics_from_result",
    "authoritative_result_metrics",
    "bell_rows_from_result",
    "chsh_margin",
    "COMPACT_SWEEP_SCHEMA_VERSION",
    "compact_sweep_payload",
    "decoy_rows_from_result",
    "expand_compact_sweep_rows",
    "expand_compact_sweep_summary",
    "extract_authoritative_metrics",
    "metric_rows_from_results",
    "mean_confidence_interval",
    "observed_metric_rows_from_results",
    "proportion_confidence_interval",
    "qber_margin",
    "secure_distance_limit",
    "summarize_metric_rows",
    "t_confidence_interval",
    "t_interval",
    "wilson_interval",
    "SWEEPABLE_TARGETS",
    "sweep_bb84_distance",
    "sweep_bb84_time",
    "sweep_scenario_parameter",
]
