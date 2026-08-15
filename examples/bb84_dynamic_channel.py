"""Sample BB84 at selected times with dynamic communication parameters."""

from __future__ import annotations

from qiskit_qkd import (
    BB84Protocol,
    ChannelCharacterizer,
    ChannelConfig,
    ConstantProfile,
    DetectorConfig,
    DynamicConfig,
    ExponentialRampProfile,
    ParameterSchedule,
    PostProcessingConfig,
    QiskitSamplerBackend,
    Scenario,
)
from qiskit_qkd.analysis import sweep_bb84_time


def main() -> None:
    scenario = Scenario(
        pulses=1_024,
        clock_rate_hz=1_000_000.0,
        seed=41,
        channel=ChannelConfig(kind="fiber", distance_km=5.0, attenuation_db_km=0.2),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.65,
            gate_width_s=1e-9,
            double_click_policy="random",
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="source.preparation_error_probability",
                    profile=ConstantProfile(start_s=0.0, end_s=3.0, value=0.08),
                ),
                ParameterSchedule(
                    target="channel.background_count_rate_hz",
                    profile=ExponentialRampProfile(
                        start_s=5.0,
                        end_s=8.0,
                        start_value=1_000.0,
                        end_value=200_000_000.0,
                        curve=3.0,
                    ),
                ),
            ),
        ),
    )
    time_points_s = [0.0, 2.0, 4.0, 5.0, 6.5, 8.0]

    channel_rows = ChannelCharacterizer().characterize_time(
        scenario,
        time_points_s=time_points_s,
    )
    bb84_rows = sweep_bb84_time(
        BB84Protocol(),
        scenario,
        time_points_s,
        backend_factory=lambda run_scenario: QiskitSamplerBackend(
            seed=run_scenario.seed,
            max_circuits_per_job=512,
            max_recorded_results=0,
        ),
    )

    print("BB84 dynamic channel characterization")
    print(
        f"{'time_s':>6} {'prep_err':>9} {'bg_rate_hz':>12} "
        f"{'eta':>8} {'qber':>8} {'sifted':>8} {'secret_bps':>11}",
    )
    for channel_row, bb84_row in zip(channel_rows, bb84_rows, strict=True):
        print(
            f"{channel_row['time_s']:6.1f} "
            f"{bb84_row['source.preparation_error_probability']:9.4f} "
            f"{bb84_row['channel.background_count_rate_hz']:12.1f} "
            f"{channel_row['transmittance']:8.4f} "
            f"{bb84_row['qber']:8.4f} "
            f"{bb84_row['sifted']:8d} "
            f"{bb84_row['secret_key_rate_bps']:11.2f}",
        )


if __name__ == "__main__":
    main()
