"""Run the minimal ideal BB84 simulation through Qiskit circuits."""

from __future__ import annotations

import json

from qiskit_qkd import (
    BB84Protocol,
    PostProcessingConfig,
    QiskitSamplerBackend,
    Scenario,
)


def main() -> None:
    scenario = Scenario(
        pulses=256,
        clock_rate_hz=1_000_000.0,
        seed=7,
        post_processing=PostProcessingConfig(
            qber_abort_threshold=0.11,
            error_correction_efficiency=1.16,
        ),
        event_sample_size=5,
    )
    backend = QiskitSamplerBackend(seed=scenario.seed)
    result = BB84Protocol().run(scenario, backend=backend)

    print("Ideal BB84 summary")
    print(json.dumps(result.summary(), indent=2, sort_keys=True))
    print("\nFirst Qiskit circuit")
    print(backend.last_circuits[0].draw("text"))


if __name__ == "__main__":
    main()
