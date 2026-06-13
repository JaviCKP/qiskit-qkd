"""Compare BB84 with ideal execution and Qiskit Aer quantum/readout noise."""

from __future__ import annotations

from qiskit_qkd import (
    BB84Protocol,
    ChannelConfig,
    DetectorConfig,
    QiskitSamplerBackend,
    Scenario,
)
from qiskit_qkd.qiskit_integration import AerNoiseModelAdapter, TranspilationOptions


def run_case(label: str, scenario: Scenario) -> tuple[str, float, dict]:
    adapter = AerNoiseModelAdapter.from_scenario(scenario)
    summary = adapter.summary()
    backend = QiskitSamplerBackend(
        seed=scenario.seed,
        seed_simulator=scenario.seed + 1,
        max_recorded_results=1,
        noise_model=adapter.noise_model if summary["enabled"] else None,
        noise_summary=summary,
        transpilation=TranspilationOptions(
            optimization_level=0,
            seed_transpiler=scenario.seed + 2,
        ),
    )
    result = BB84Protocol().run(scenario, backend=backend)
    return label, result.metrics.qber, result.qiskit


def main() -> None:
    seed = 101
    base = {
        "pulses": 512,
        "clock_rate_hz": 1_000_000.0,
        "seed": seed,
    }
    cases = [
        ("ideal", Scenario(**base)),
        (
            "depolarizing",
            Scenario(
                **base,
                channel=ChannelConfig(depolarizing_probability=1.0),
            ),
        ),
        (
            "phase_damping",
            Scenario(
                **base,
                channel=ChannelConfig(phase_damping_probability=1.0),
            ),
        ),
        (
            "readout",
            Scenario(
                **base,
                detector=DetectorConfig(readout_error_probability=0.2),
            ),
        ),
    ]

    print("BB84 Aer noisy comparison")
    print(f"{'case':<16} {'qber':>8} {'primitive':>18} NoiseModel")
    for label, scenario in cases:
        name, qber, qiskit_summary = run_case(label, scenario)
        noise = qiskit_summary["noise_model"]
        components = ",".join(noise.get("components", [])) or "none"
        print(
            f"{name:<16} {qber:8.4f} "
            f"{qiskit_summary['primitive']:>18} {components}",
        )


if __name__ == "__main__":
    main()
