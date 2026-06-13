"""Generic optional plotting functions for plot-ready analysis rows."""

from __future__ import annotations

import importlib
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .style import QKD_COLORS, compact_value, metric_label

RowValue = str | int | float | bool | None


def plot_metric_sweep(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    x: str,
    y: str | Sequence[str],
    title: str | None = None,
    log_y: bool | Sequence[str] = False,
    threshold_lines: Mapping[str, Sequence[float]] | None = None,
    marker: str = "o",
    figsize: tuple[float, float] | None = None,
) -> Any:
    """Plot one or more metrics against a sweep column."""

    plt = _require_pyplot()
    row_list = list(rows)
    y_keys = (y,) if isinstance(y, str) else tuple(y)
    if not y_keys:
        raise ValueError("y must contain at least one metric")
    figure, axes = plt.subplots(
        len(y_keys),
        1,
        sharex=True,
        figsize=figsize or (7.0, max(2.8, 2.4 * len(y_keys))),
    )
    axes_list = _axes_list(axes)
    log_keys = _log_metric_keys(log_y, y_keys)

    for index, (axis, y_key) in enumerate(zip(axes_list, y_keys, strict=True)):
        xs, ys = _series(row_list, x=x, y=y_key)
        axis.plot(
            xs,
            ys,
            marker=marker,
            color=QKD_COLORS[index % len(QKD_COLORS)],
            label=metric_label(y_key),
        )
        axis.set_ylabel(metric_label(y_key))
        axis.grid(True, alpha=0.25)
        if y_key in log_keys and any(value > 0.0 for value in ys):
            axis.set_yscale("log")
        for threshold in (threshold_lines or {}).get(y_key, ()):
            axis.axhline(
                threshold,
                color="#666666",
                linestyle="--",
                linewidth=1.0,
            )
        if index == 0 and title is not None:
            axis.set_title(title)
    axes_list[-1].set_xlabel(metric_label(x))
    figure.tight_layout()
    return figure


def plot_threshold_curve(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    x: str,
    y: str,
    threshold: float,
    title: str | None = None,
) -> Any:
    """Plot a single metric sweep with a horizontal threshold line."""

    return plot_metric_sweep(
        rows,
        x=x,
        y=y,
        title=title,
        threshold_lines={y: (threshold,)},
    )


def plot_metric_grid(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    x: str,
    y: str,
    z: str,
    title: str | None = None,
    cmap: str = "viridis",
    figsize: tuple[float, float] | None = None,
) -> Any:
    """Plot a heatmap from rows containing x/y coordinates and a metric z."""

    plt = _require_pyplot()
    row_list = list(rows)
    x_values = sorted(
        {
            value
            for row in row_list
            for value in [_plot_value(row.get(x))]
            if value is not None
        },
    )
    y_values = sorted(
        {
            value
            for row in row_list
            for value in [_plot_value(row.get(y))]
            if value is not None
        },
    )
    if not x_values or not y_values:
        raise ValueError("rows must contain at least one complete grid point")
    index_by_x = {value: index for index, value in enumerate(x_values)}
    index_by_y = {value: index for index, value in enumerate(y_values)}
    grid = [[math.nan for _x in x_values] for _y in y_values]
    for row in row_list:
        x_value = _plot_value(row.get(x))
        y_value = _plot_value(row.get(y))
        z_value = _numeric(_row_value(row, z))
        if x_value is None or y_value is None or z_value is None:
            continue
        grid[index_by_y[y_value]][index_by_x[x_value]] = z_value

    figure, axis = plt.subplots(1, 1, figsize=figsize or (6.4, 4.4))
    image = axis.imshow(grid, origin="lower", aspect="auto", cmap=cmap)
    axis.set_xlabel(metric_label(x))
    axis.set_ylabel(metric_label(y))
    axis.set_xticks(range(len(x_values)))
    axis.set_yticks(range(len(y_values)))
    axis.set_xticklabels([compact_value(value) for value in x_values])
    axis.set_yticklabels([compact_value(value) for value in y_values])
    if title is not None:
        axis.set_title(title)
    figure.colorbar(image, ax=axis, label=metric_label(z))
    figure.tight_layout()
    return figure


def plot_stacked_counts(
    rows: Iterable[Mapping[str, RowValue]],
    *,
    x: str,
    counts: Sequence[str],
    title: str | None = None,
    figsize: tuple[float, float] | None = None,
) -> Any:
    """Plot stacked count columns for each row."""

    if not counts:
        raise ValueError("counts must contain at least one metric")
    plt = _require_pyplot()
    row_list = list(rows)
    labels = [compact_value(row.get(x)) for row in row_list]
    positions = list(range(len(row_list)))
    bottom = [0.0 for _row in row_list]
    figure, axis = plt.subplots(1, 1, figsize=figsize or (7.0, 4.0))
    for index, count_key in enumerate(counts):
        heights = [
            _numeric(row.get(count_key)) or 0.0
            for row in row_list
        ]
        axis.bar(
            positions,
            heights,
            bottom=bottom,
            label=metric_label(count_key),
            color=QKD_COLORS[index % len(QKD_COLORS)],
        )
        bottom = [
            prior + height
            for prior, height in zip(bottom, heights, strict=True)
        ]
    axis.set_xlabel(metric_label(x))
    axis.set_ylabel("Count")
    axis.set_xticks(positions)
    axis.set_xticklabels(labels)
    axis.legend()
    axis.grid(True, axis="y", alpha=0.25)
    if title is not None:
        axis.set_title(title)
    figure.tight_layout()
    return figure


def save_figure(
    figure: Any,
    path: str | Path,
    *,
    dpi: int = 160,
    bbox_inches: str = "tight",
) -> None:
    """Save a Matplotlib figure with repository defaults."""

    figure.savefig(path, dpi=dpi, bbox_inches=bbox_inches)


def _require_pyplot() -> Any:
    try:
        return importlib.import_module("matplotlib.pyplot")
    except ModuleNotFoundError as exc:
        missing = exc.name or str(exc)
        if "matplotlib" in missing:
            raise ImportError(
                "Visualization requires matplotlib. Install with "
                '`python -m pip install -e ".[plot]"` or '
                '`python -m pip install "qiskit-qkd[plot]"`.',
            ) from exc
        raise


def _axes_list(axes: Any) -> list[Any]:
    if isinstance(axes, list | tuple):
        return list(axes)
    if hasattr(axes, "flatten"):
        return list(axes.flatten())
    return [axes]


def _log_metric_keys(log_y: bool | Sequence[str], y_keys: tuple[str, ...]) -> set[str]:
    if isinstance(log_y, bool):
        return set(y_keys) if log_y else set()
    return set(log_y)


def _series(
    rows: Sequence[Mapping[str, RowValue]],
    *,
    x: str,
    y: str,
) -> tuple[list[float], list[float]]:
    points = [
        (x_value, y_value)
        for row in rows
        for x_value, y_value in [(_numeric(row.get(x)), _numeric(_row_value(row, y)))]
        if x_value is not None and y_value is not None
    ]
    points.sort(key=lambda point: point[0])
    return [point[0] for point in points], [point[1] for point in points]


def _row_value(row: Mapping[str, RowValue], key: str) -> RowValue:
    if key in row:
        return row[key]
    mean_key = f"{key}_mean"
    if mean_key in row:
        return row[mean_key]
    return None


def _numeric(value: RowValue) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, int | float):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _plot_value(value: RowValue) -> float | str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        value = float(value)
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    return None
