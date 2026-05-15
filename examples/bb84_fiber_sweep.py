"""Sweep BB84 over fiber distances and print distance-dependent rates."""

from __future__ import annotations

from qiskit_qkd import (
    BB84Protocol,
    ChannelConfig,
    DetectorConfig,
    PostProcessingConfig,
    QiskitSamplerBackend,
    Scenario,
)
from qiskit_qkd.analysis import sweep_bb84_distance


def main() -> None:
    scenario = Scenario(
        pulses=4_096,
        clock_rate_hz=1_000_000.0,
        seed=7,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=0.0,
            attenuation_db_km=0.2,
            fixed_loss_db=0.0,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.2,
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
        [0, 10, 25, 50, 75, 100],
        backend_factory=lambda run_scenario: QiskitSamplerBackend(
            seed=run_scenario.seed,
            max_circuits_per_job=512,
            max_recorded_results=0,
        ),
    )

    print("BB84 fiber sweep")
    print(
        f"{'km':>6} {'loss_dB':>8} {'detected':>9} {'gain':>10} "
        f"{'sifted':>8} {'QBER':>8} {'secret_bps':>12}",
    )
    for row in rows:
        print(
            f"{row['distance_km']:6.1f} "
            f"{row['loss_db']:8.2f} "
            f"{row['detected']:9d} "
            f"{row['gain']:10.5f} "
            f"{row['sifted']:8d} "
            f"{row['qber']:8.4f} "
            f"{row['secret_key_rate_bps']:12.2f}",
        )


if __name__ == "__main__":
    main()
