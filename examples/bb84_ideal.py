"""Run the minimal ideal BB84 simulation through Qiskit circuits."""

from __future__ import annotations

import json
import sys
import warnings

from qiskit_qkd import (
    BB84Protocol,
    PostProcessingConfig,
    Scenario,
)
from qiskit_qkd.backends import backend_from_scenario

_BOX_DRAWING_ASCII = str.maketrans(
    {
        "\u2500": "-",
        "\u2502": "|",
        "\u250c": "+",
        "\u2510": "+",
        "\u2514": "+",
        "\u2518": "+",
        "\u251c": "+",
        "\u2524": "+",
        "\u252c": "+",
        "\u2534": "+",
        "\u253c": "+",
        "\u2550": "=",
        "\u2551": "|",
        "\u2554": "+",
        "\u2557": "+",
        "\u255a": "+",
        "\u255d": "+",
        "\u2560": "+",
        "\u2563": "+",
        "\u2566": "+",
        "\u2569": "+",
        "\u256c": "+",
        "\u2565": "+",
        "\u2568": "+",
        "\u256b": "+",
    },
)


def _console_safe_text(value: object) -> str:
    text = str(value).translate(_BOX_DRAWING_ASCII)
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding)


def _draw_console_safe_circuit(circuit: object) -> str:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="The encoding .* has a limited charset.*",
            category=RuntimeWarning,
        )
        return _console_safe_text(circuit.draw("text"))


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
    backend = backend_from_scenario(scenario)
    result = BB84Protocol().run(scenario, backend=backend)

    print("Ideal BB84 summary")
    print(json.dumps(result.summary(), indent=2, sort_keys=True))
    print("\nFirst Qiskit circuit")
    print(_draw_console_safe_circuit(backend.last_circuits[0]))


if __name__ == "__main__":
    main()
