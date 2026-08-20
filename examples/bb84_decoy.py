"""Run BB84 with weak-coherent decoy intensities and per-class statistics."""

from __future__ import annotations

from qiskit_qkd import (
    BB84Protocol,
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    PostProcessingConfig,
    Scenario,
    SourceConfig,
    decoy_rows_from_result,
)
from qiskit_qkd.backends import backend_from_scenario


def main() -> None:
    scenario = Scenario(
        pulses=4_096,
        clock_rate_hz=1_000_000.0,
        seed=61,
        source=SourceConfig(
            kind="weak_coherent",
            decoy_intensities=(
                DecoyIntensity(
                    "signal",
                    mean_photon_number=0.6,
                    selection_probability=0.7,
                ),
                DecoyIntensity(
                    "decoy",
                    mean_photon_number=0.2,
                    selection_probability=0.2,
                ),
                DecoyIntensity(
                    "vacuum",
                    mean_photon_number=0.0,
                    selection_probability=0.1,
                ),
            ),
        ),
        channel=ChannelConfig(kind="fiber", distance_km=10.0, attenuation_db_km=0.2),
        detector=DetectorConfig(kind="threshold", efficiency=0.8),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    backend = backend_from_scenario(scenario)
    # Keep the example's bounded-output settings without bypassing resolution.
    backend.max_circuits_per_job = 512
    backend.max_recorded_results = 0
    result = BB84Protocol().run(scenario, backend=backend)

    print("BB84 decoy-state source comparison")
    print(
        f"{'class':>8} {'mu':>6} {'p_sel':>7} {'pulses':>7} "
        f"{'emitted':>8} {'multi':>7} {'surv':>7} {'gain':>8} {'qber':>8}",
    )
    for name in ("signal", "decoy", "vacuum"):
        row = result.decoy[name]
        print(
            f"{name:>8} "
            f"{row['mean_photon_number']:6.3f} "
            f"{row['selection_probability']:7.3f} "
            f"{row['pulses']:7d} "
            f"{row['emitted']:8d} "
            f"{row['multi_photon']:7d} "
            f"{row['surviving_photons']:7d} "
            f"{row['gain']:8.4f} "
            f"{row['qber']:8.4f}",
        )

    security = result.decoy["security"]
    print("\nAsymptotic vacuum+weak decoy estimate")
    print(
        f"  Y1_L={security['single_photon_yield_lower_bound']:.6f} "
        f"e1_U={security['single_photon_error_rate_upper_bound']:.6f} "
        f"Q1_L={security['single_photon_gain_lower_bound']:.6f} "
        f"secret_bps={security['secret_key_rate_bps']:.2f}",
    )
    print(
        "\nPlot-ready rows available through "
        f"decoy_rows_from_result(result): {len(decoy_rows_from_result(result))}",
    )


if __name__ == "__main__":
    main()
