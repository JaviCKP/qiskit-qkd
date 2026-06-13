from __future__ import annotations

import importlib
from pathlib import Path

import pytest


class FakeFigure:
    def __init__(self, axes):
        self.axes = axes
        self.colorbars: list[dict[str, object]] = []
        self.saved: list[tuple[Path, dict[str, object]]] = []
        self.tight = False

    def colorbar(self, image, *, ax=None, label=None):
        self.colorbars.append({"image": image, "ax": ax, "label": label})

    def savefig(self, path, **kwargs):
        self.saved.append((Path(path), kwargs))

    def tight_layout(self) -> None:
        self.tight = True


class FakeAxes:
    def __init__(self) -> None:
        self.plots: list[dict[str, object]] = []
        self.bars: list[dict[str, object]] = []
        self.images: list[dict[str, object]] = []
        self.hlines: list[dict[str, object]] = []
        self.labels: dict[str, object] = {}
        self.legend_called = False
        self.grid_called = False
        self.yscale = "linear"

    def plot(self, xs, ys, **kwargs):
        self.plots.append({"xs": list(xs), "ys": list(ys), **kwargs})

    def bar(self, xs, heights, **kwargs):
        self.bars.append({"xs": list(xs), "heights": list(heights), **kwargs})

    def imshow(self, image, **kwargs):
        self.images.append({"image": image, **kwargs})
        return image

    def axhline(self, y, **kwargs):
        self.hlines.append({"y": y, **kwargs})

    def set_xlabel(self, value):
        self.labels["xlabel"] = value

    def set_ylabel(self, value):
        self.labels["ylabel"] = value

    def set_title(self, value):
        self.labels["title"] = value

    def set_xticks(self, values):
        self.labels["xticks"] = list(values)

    def set_yticks(self, values):
        self.labels["yticks"] = list(values)

    def set_xticklabels(self, values):
        self.labels["xticklabels"] = list(values)

    def set_yticklabels(self, values):
        self.labels["yticklabels"] = list(values)

    def set_yscale(self, value):
        self.yscale = value

    def grid(self, *args, **kwargs):
        self.grid_called = True

    def legend(self, *args, **kwargs):
        self.legend_called = True


class FakePyplot:
    def __init__(self) -> None:
        self.figures: list[FakeFigure] = []

    def subplots(self, nrows=1, ncols=1, **_kwargs):
        axes = [FakeAxes() for _ in range(nrows * ncols)]
        figure = FakeFigure(axes)
        self.figures.append(figure)
        if len(axes) == 1:
            return figure, axes[0]
        return figure, axes


def test_plot_metric_sweep_requires_optional_matplotlib(monkeypatch) -> None:
    from qiskit_qkd.visualization import plot_metric_sweep

    real_import_module = importlib.import_module

    def fail_for_matplotlib(name: str):
        if name == "matplotlib.pyplot":
            raise ModuleNotFoundError("No module named 'matplotlib'")
        return real_import_module(name)

    monkeypatch.setattr(importlib, "import_module", fail_for_matplotlib)

    with pytest.raises(ImportError, match=r"qiskit-qkd\[plot\]"):
        plot_metric_sweep(
            [{"distance_km": 0.0, "qber": 0.02}],
            x="distance_km",
            y="qber",
        )


def test_plot_metric_sweep_builds_one_axis_per_metric(monkeypatch) -> None:
    from qiskit_qkd.visualization import plots

    fake_pyplot = FakePyplot()
    monkeypatch.setattr(plots, "_require_pyplot", lambda: fake_pyplot)

    figure = plots.plot_metric_sweep(
        [
            {"distance_km": 0.0, "qber": 0.01, "secret_key_rate_bps": 100.0},
            {"distance_km": 10.0, "qber": 0.03, "secret_key_rate_bps": 10.0},
        ],
        x="distance_km",
        y=("qber", "secret_key_rate_bps"),
        title="BB84 distance summary",
        log_y=("secret_key_rate_bps",),
        threshold_lines={"qber": (0.11,)},
    )

    assert figure.axes[0].plots[0]["xs"] == [0.0, 10.0]
    assert figure.axes[0].plots[0]["ys"] == [0.01, 0.03]
    assert figure.axes[0].hlines[0]["y"] == 0.11
    assert figure.axes[0].labels["title"] == "BB84 distance summary"
    assert figure.axes[1].yscale == "log"
    assert figure.axes[1].labels["xlabel"] == "Distance (km)"


def test_plot_metric_grid_pivots_rows_into_sorted_matrix(monkeypatch) -> None:
    from qiskit_qkd.visualization import plots

    fake_pyplot = FakePyplot()
    monkeypatch.setattr(plots, "_require_pyplot", lambda: fake_pyplot)

    figure = plots.plot_metric_grid(
        [
            {"distance_km": 10.0, "dark_count_rate_hz": 100.0, "qber": 0.10},
            {"distance_km": 0.0, "dark_count_rate_hz": 100.0, "qber": 0.01},
            {"distance_km": 10.0, "dark_count_rate_hz": 1_000.0, "qber": 0.20},
            {"distance_km": 0.0, "dark_count_rate_hz": 1_000.0, "qber": 0.03},
        ],
        x="distance_km",
        y="dark_count_rate_hz",
        z="qber",
    )

    assert figure.axes[0].images[0]["image"] == [[0.01, 0.10], [0.03, 0.20]]
    assert figure.axes[0].labels["xticklabels"] == ["0", "10"]
    assert figure.axes[0].labels["yticklabels"] == ["100", "1000"]
    assert figure.colorbars[0]["label"] == "QBER"


def test_recipes_and_save_figure_use_plot_helpers(monkeypatch, tmp_path) -> None:
    from qiskit_qkd.visualization import (
        plot_bb84_distance_summary,
        plot_e91_chsh_summary,
        plots,
        save_figure,
    )

    fake_pyplot = FakePyplot()
    monkeypatch.setattr(plots, "_require_pyplot", lambda: fake_pyplot)

    distance_figure = plot_bb84_distance_summary(
        [
            {
                "distance_km": 0.0,
                "qber": 0.01,
                "gain": 1.0,
                "secret_key_rate_bps": 500.0,
            },
        ],
    )
    bell_figure = plot_e91_chsh_summary(
        [
            {
                "alice_setting": 0,
                "bob_setting": 0,
                "correlation": -0.7,
            },
        ],
        chsh_s=2.65,
    )

    output = tmp_path / "figure.svg"
    save_figure(distance_figure, output)

    assert len(distance_figure.axes) == 3
    assert bell_figure.axes[0].labels["title"] == "E91 CHSH correlations (S=2.650)"
    assert distance_figure.saved[0][0] == output
    assert distance_figure.saved[0][1]["bbox_inches"] == "tight"
