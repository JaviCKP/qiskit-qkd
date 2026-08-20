"""Run entanglement-based E91 and print Bell-test diagnostics."""

from __future__ import annotations

from qiskit_qkd import (
    ChannelConfig,
    DetectorConfig,
    E91Config,
    E91Protocol,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
    bell_rows_from_result,
)
from qiskit_qkd.backends import backend_from_scenario


def build_scenario(*, source_preparation_error: float = 0.0) -> Scenario:
    return Scenario(
        pulses=2_048,
        clock_rate_hz=1_000_000.0,
        seed=91,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            emission_probability=1.0,
            preparation_error_probability=source_preparation_error,
        ),
        channel=ChannelConfig(kind="ideal"),
        detector=DetectorConfig(kind="threshold", efficiency=1.0),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )


def run_case(label: str, scenario: Scenario) -> None:
    backend = backend_from_scenario(scenario)
    backend.max_circuits_per_job = 512
    backend.max_recorded_results = 0
    result = E91Protocol().run(scenario, backend=backend)
    print(label)
    print(
        f"  coincidences={result.metrics.detected} "
        f"key_rounds={result.metrics.sifted} "
        f"qber={result.metrics.qber:.4f} "
        f"CHSH S={result.metrics.chsh_s:.4f} "
        f"violation={result.bell['bell_violation']}",
    )
    print("  setting correlations")
    for row in bell_rows_from_result(result):
        if row["used_for_chsh"] or row["used_for_key"]:
            print(
                f"    {row['setting_pair']:>5} "
                f"corr={row['correlation']:>7.4f} "
                f"coinc={row['coincidences']:>4} "
                f"key={row['used_for_key']} "
                f"chsh={row['used_for_chsh']}",
            )


def main() -> None:
    run_case("Ideal E91 singlet", build_scenario())
    run_case(
        "\nNoisy source E91",
        build_scenario(source_preparation_error=0.35),
    )


if __name__ == "__main__":
    main()
