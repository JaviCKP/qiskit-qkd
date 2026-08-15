"""Optional plotting helpers for QKD analysis rows.

Install the ``plot`` extra before calling plotting functions:
``python -m pip install -e ".[plot]"``.
"""

from .plots import (
    plot_metric_grid,
    plot_metric_sweep,
    plot_stacked_counts,
    plot_threshold_curve,
    save_figure,
)
from .recipes import (
    plot_bb84_distance_summary,
    plot_channel_comparison,
    plot_decoy_security_summary,
    plot_e91_chsh_summary,
    plot_eve_tradeoff,
    plot_timing_summary,
)
from .style import QKD_COLORS, metric_label

__all__ = [
    "QKD_COLORS",
    "metric_label",
    "plot_bb84_distance_summary",
    "plot_channel_comparison",
    "plot_decoy_security_summary",
    "plot_e91_chsh_summary",
    "plot_eve_tradeoff",
    "plot_metric_grid",
    "plot_metric_sweep",
    "plot_stacked_counts",
    "plot_threshold_curve",
    "plot_timing_summary",
    "save_figure",
]
