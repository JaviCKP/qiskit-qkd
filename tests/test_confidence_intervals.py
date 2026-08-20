from __future__ import annotations

import pytest

from qiskit_qkd.analysis import (
    summarize_metric_rows,
    t_interval,
    wilson_interval,
)


def test_wilson_interval_has_known_95_percent_bounds_and_probability_limits() -> None:
    interval = wilson_interval(5, 10)

    assert interval.level == 0.95
    assert interval.method == "wilson"
    assert interval.n == 10
    assert interval.bounds == pytest.approx(
        (0.2365930905, 0.7634069095),
    )
    assert 0.0 <= interval.lower <= interval.upper <= 1.0
    assert interval.to_dict() == {
        "level": 0.95,
        "method": "wilson",
        "n": 10,
        "bounds": [interval.lower, interval.upper],
    }


@pytest.mark.parametrize("successes", [0, 1])
def test_wilson_interval_is_defined_for_one_trial(successes: int) -> None:
    interval = wilson_interval(successes, 1)

    assert interval.n == 1
    assert interval.lower is not None
    assert interval.upper is not None
    assert 0.0 <= interval.lower <= interval.upper <= 1.0


def test_wilson_interval_marks_zero_denominator_undefined() -> None:
    interval = wilson_interval(0, 0)

    assert interval.n == 0
    assert interval.bounds == (None, None)
    assert interval.to_dict()["bounds"] == [None, None]


def test_t_interval_uses_repeat_variance_and_is_undefined_below_two_repeats() -> None:
    interval = t_interval([1.0, 2.0, 3.0])

    assert interval.method == "t"
    assert interval.n == 3
    assert interval.bounds == pytest.approx(
        (-0.4841377118, 4.4841377118),
    )
    assert t_interval([]).to_dict() == {
        "level": 0.95,
        "method": "t",
        "n": 0,
        "bounds": [None, None],
    }
    assert t_interval([1.0]).bounds == (None, None)


def test_summary_adds_count_based_wilson_and_binary_decision_intervals() -> None:
    rows = [
        {
            "group": "baseline",
            "qber": 0.1,
            "errors": 1,
            "sifted": 10,
            "detected": 8,
            "pulses": 10,
            "threshold_exceeded": False,
        },
        {
            "group": "baseline",
            "qber": 0.2,
            "errors": 2,
            "sifted": 20,
            "detected": 7,
            "pulses": 20,
            "threshold_exceeded": True,
        },
        {
            "group": "baseline",
            "qber": 0.3,
            "errors": 0,
            "sifted": 0,
            "detected": 0,
            "pulses": 0,
            "threshold_exceeded": False,
        },
    ]

    summary = summarize_metric_rows(
        rows,
        group_by=("group",),
        metrics=("qber",),
    )[0]

    assert summary["qber_ci"] == {
        "level": 0.95,
        "method": "wilson",
        "n": 30,
        "bounds": pytest.approx(
            [0.034599889, 0.256210826],
        ),
    }
    assert summary["gain_ci"]["method"] == "wilson"
    assert summary["gain_ci"]["n"] == 30
    assert summary["threshold_decision_ci"]["method"] == "wilson"
    assert summary["threshold_decision_ci"]["n"] == 3
    assert summary["threshold_decision_ci"]["bounds"] == pytest.approx(
        [0.06149194, 0.7923404],
    )
    # Quantiles remain descriptive dispersion fields, not confidence bounds.
    assert "qber_p05" in summary
    assert summary["qber_ci"]["bounds"] != [summary["qber_p05"], summary["qber_p95"]]


def test_summary_ci_is_undefined_when_no_finite_repeat_values_exist() -> None:
    summary = summarize_metric_rows(
        [{"group": "empty", "qber": None}],
        group_by=("group",),
        metrics=("qber",),
    )[0]

    assert summary["qber_ci"] == {
        "level": 0.95,
        "method": "t",
        "n": 0,
        "bounds": [None, None],
    }
