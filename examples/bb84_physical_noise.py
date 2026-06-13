"""Compare BB84 with layered source, coherent-channel, and background noise."""

from __future__ import annotations

import math

from qiskit_qkd import (
    BB84Protocol,
    ChannelConfig,
    DetectorConfig,
    Scenario,
    SourceConfig,
)


def run_case(label: str, scenario: Scenario) -> tuple[str, float, int, int, str]:
    result = BB84Protocol().run(scenario)
    origins = {
        event.detection_origin
        for event in result.event_sample
        if event.detection_origin != "none"
    }
    origin_summary = ",".join(sorted(origins)) or "signal"
    return (
        label,
        result.metrics.qber,
        result.metrics.detected,
        result.metrics.sifted,
        origin_summary,
    )


def main() -> None:
    base = {
        "pulses": 512,
        "clock_rate_hz": 1_000_000.0,
        "seed": 211,
        "event_sample_size": 32,
    }
    cases = [
        ("ideal", Scenario(**base)),
        (
            "preparation",
            Scenario(
                **base,
                source=SourceConfig(preparation_error_probability=1.0),
            ),
        ),
        (
            "misalignment",
            Scenario(
                **base,
                channel=ChannelConfig(polarization_rotation_y_rad=math.pi),
            ),
        ),
        (
            "background",
            Scenario(
                **base,
                source=SourceConfig(emission_probability=0.0),
                channel=ChannelConfig(background_count_rate_hz=20_000_000.0),
                detector=DetectorConfig(gate_width_s=1e-6),
            ),
        ),
    ]

    print("BB84 physical noise comparison")
    print(f"{'case':<14} {'qber':>8} {'detected':>9} {'sifted':>8} event-layer")
    for label, scenario in cases:
        name, qber, detected, sifted, origin_summary = run_case(label, scenario)
        print(
            f"{name:<14} {qber:8.4f} {detected:9d} {sifted:8d} "
            f"{origin_summary}",
        )


if __name__ == "__main__":
    main()
