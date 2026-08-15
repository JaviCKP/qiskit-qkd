"""Generate a BB84 distance-sweep figure when the optional plot extra is installed."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from qiskit_qkd import (
    BB84Protocol,
    ChannelConfig,
    DetectorConfig,
    PostProcessingConfig,
    QiskitSamplerBackend,
    Scenario,
)
from qiskit_qkd.analysis import add_derived_metrics, sweep_bb84_distance
from qiskit_qkd.visualization import plot_bb84_distance_summary, save_figure


def main() -> None:
    print("BB84 visualization demo")
    if importlib.util.find_spec("matplotlib") is None:
        print('requires qiskit-qkd[plot]: python -m pip install -e ".[plot]"')
        return

    import matplotlib

    matplotlib.use("Agg")

    scenario = Scenario(
        pulses=1_024,
        clock_rate_hz=1_000_000.0,
        seed=107,
        channel=ChannelConfig(kind="fiber", distance_km=0.0, attenuation_db_km=0.2),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.25,
            dark_count_rate_hz=100.0,
            gate_width_s=1e-9,
            double_click_policy="discard",
        ),
        post_processing=PostProcessingConfig(
            qber_abort_threshold=0.11,
            error_correction_efficiency=1.16,
        ),
    )
    rows = sweep_bb84_distance(
        BB84Protocol(),
        scenario,
        [0, 10, 25, 50, 75],
        backend_factory=lambda run_scenario: QiskitSamplerBackend(
            seed=run_scenario.seed,
            max_circuits_per_job=256,
            max_recorded_results=0,
        ),
    )
    rows = add_derived_metrics(
        rows,
        qber_abort_threshold=scenario.post_processing.qber_abort_threshold,
    )
    figure = plot_bb84_distance_summary(
        rows,
        qber_threshold=scenario.post_processing.qber_abort_threshold or 0.11,
    )

    output = Path(__file__).resolve().parent / "figures" / "bb84_distance_summary.svg"
    output.parent.mkdir(exist_ok=True)
    save_figure(figure, output)
    print("saved examples/figures/bb84_distance_summary.svg")


if __name__ == "__main__":
    main()
