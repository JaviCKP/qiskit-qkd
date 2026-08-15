"""Compare BB84 without Eve and with intercept-resend attacks."""

from __future__ import annotations

from dataclasses import replace

from qiskit_qkd import (
    BB84Protocol,
    EveConfig,
    PostProcessingConfig,
    QiskitSamplerBackend,
    Scenario,
)


def run_case(label: str, scenario: Scenario) -> dict[str, float | int | str]:
    result = BB84Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(
            seed=scenario.seed,
            max_circuits_per_job=512,
            max_recorded_results=0,
        ),
    )
    return {
        "case": label,
        "intercept_probability": scenario.eavesdropper.intercept_probability,
        "qber": result.metrics.qber,
        "sifted": result.metrics.sifted,
        "eve_intercepted_fraction": result.metrics.eve_intercepted_fraction,
        "eve_information_estimate": result.metrics.eve_information_estimate,
        "secret_key_rate_bps": result.metrics.secret_key_rate_bps,
    }


def main() -> None:
    base = Scenario(
        pulses=2_048,
        clock_rate_hz=1_000_000.0,
        seed=53,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )
    scenarios = [
        ("no_eve", base),
        (
            "intercept_25",
            replace(
                base,
                seed=54,
                eavesdropper=EveConfig(
                    kind="intercept_resend",
                    intercept_probability=0.25,
                ),
            ),
        ),
        (
            "intercept_100",
            replace(
                base,
                seed=55,
                eavesdropper=EveConfig(
                    kind="intercept_resend",
                    intercept_probability=1.0,
                ),
            ),
        ),
    ]
    rows = [run_case(label, scenario) for label, scenario in scenarios]

    print("BB84 Eve intercept-resend comparison")
    print(
        f"{'case':>14} {'p_int':>7} {'qber':>8} {'sifted':>8} "
        f"{'eve_frac':>9} {'eve_info':>9} {'secret_bps':>11}",
    )
    for row in rows:
        print(
            f"{row['case']:>14} "
            f"{row['intercept_probability']:7.2f} "
            f"{row['qber']:8.4f} "
            f"{row['sifted']:8d} "
            f"{row['eve_intercepted_fraction']:9.4f} "
            f"{row['eve_information_estimate']:9.4f} "
            f"{row['secret_key_rate_bps']:11.2f}",
        )


if __name__ == "__main__":
    main()
