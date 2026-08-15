"""Domain-specific plotting recipes built on the generic row plotters."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from qiskit_qkd.results import Event, SimulationResult

from . import plots

RowValue = str | int | float | bool | None


def plot_bb84_distance_summary(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    qber_threshold: float = 0.11,
) -> Any:
    """Plot secret rate, QBER, and gain over a BB84 distance sweep."""

    return plots.plot_metric_sweep(
        rows,
        x="distance_km",
        y=("secret_key_rate_bps", "qber", "gain"),
        title="BB84 distance summary",
        log_y=("secret_key_rate_bps",),
        threshold_lines={"qber": (qber_threshold,)},
    )


def plot_channel_comparison(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    x: str = "distance_km",
) -> Any:
    """Plot loss, gain, and secret rate for channel comparison rows."""

    return plots.plot_metric_sweep(
        rows,
        x=x,
        y=("loss_db", "gain", "secret_key_rate_bps"),
        title="Channel comparison",
        log_y=("secret_key_rate_bps",),
    )


def plot_eve_tradeoff(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    x: str = "eve_intercepted_fraction",
) -> Any:
    """Plot Eve information, QBER, and secret rate trade-offs."""

    return plots.plot_metric_sweep(
        rows,
        x=x,
        y=("qber", "eve_information_estimate", "secret_key_rate_bps"),
        title="Eve trade-off",
        log_y=("secret_key_rate_bps",),
    )


def plot_e91_chsh_summary(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    chsh_s: float | None = None,
) -> Any:
    """Plot an E91 setting-correlation heatmap."""

    title = "E91 CHSH correlations"
    if chsh_s is not None:
        title = f"{title} (S={chsh_s:.3f})"
    return plots.plot_metric_grid(
        rows,
        x="bob_setting",
        y="alice_setting",
        z="correlation",
        title=title,
        cmap="coolwarm",
    )


def plot_decoy_security_summary(
    rows: Iterable[Mapping[str, RowValue]],
) -> Any:
    """Plot decoy intensity gain and QBER rows."""

    intensity_rows = [
        row
        for row in rows
        if row.get("row_type") == "intensity"
        and row.get("intensity_class") is not None
    ]
    return plots.plot_metric_sweep(
        intensity_rows,
        x="mean_photon_number",
        y=("gain", "qber"),
        title="Decoy intensity summary",
    )


def plot_timing_summary(
    result_or_events: SimulationResult | Sequence[Event],
) -> Any:
    """Plot timing-status counts from a result or an explicit event sequence."""

    events = (
        result_or_events.event_sample
        if isinstance(result_or_events, SimulationResult)
        else result_or_events
    )
    counts = Counter(event.timing_status for event in events)
    rows = [
        {"timing_status": status, "events": count}
        for status, count in sorted(counts.items())
    ]
    return plots.plot_stacked_counts(
        rows,
        x="timing_status",
        counts=("events",),
        title="Timing status counts",
    )
