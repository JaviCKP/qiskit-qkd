import math

import pytest
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

from qiskit_qkd import Scenario, SimulationResult
from qiskit_qkd.backends import QiskitSamplerBackend
from qiskit_qkd.protocols import BB84Protocol


@pytest.mark.parametrize(
    ("bit", "basis"),
    [
        (0, "Z"),
        (1, "Z"),
        (0, "X"),
        (1, "X"),
    ],
)
def test_qiskit_sampler_backend_preserves_bits_for_matching_bases(
    bit: int,
    basis: str,
) -> None:
    backend = QiskitSamplerBackend(seed=17)

    assert backend.measure_bb84(bit, basis, basis) == bit


def test_qiskit_sampler_backend_records_circuits_and_counts() -> None:
    backend = QiskitSamplerBackend(seed=17)

    measured = backend.measure_bb84(1, "X", "X")

    assert measured == 1
    assert len(backend.last_circuits) == 1
    assert isinstance(backend.last_circuits[0], QuantumCircuit)
    assert backend.last_circuits[0].metadata["protocol"] == "BB84"
    assert backend.last_counts == [{"1": 1}]


def test_noiseless_bb84_statevector_sampling_uses_probabilities_with_seed() -> None:
    backend = QiskitSamplerBackend(
        seed=17,
        max_recorded_results=0,
        channel_rotation_y_rad=math.pi / 4,
    )

    bits = backend.measure_bb84_batch([(0, "Z", "Z")] * 400)

    ones = sum(bits)
    assert 0 < ones < 120


def test_external_sampler_counts_are_sampled_not_majority_voted() -> None:
    backend = QiskitSamplerBackend(
        sampler=StatevectorSampler(seed=17),
        seed=17,
        shots_per_circuit=1024,
        max_recorded_results=0,
    )

    bits = backend.measure_bb84_batch([(0, "Z", "X")] * 400)

    ones = sum(bits)
    assert 150 <= ones <= 250


def test_qiskit_sampler_backend_limits_recorded_execution_artifacts() -> None:
    backend = QiskitSamplerBackend(seed=17, max_recorded_results=2)

    bits = backend.measure_bb84_batch(
        [
            (0, "Z", "Z"),
            (1, "Z", "Z"),
            (0, "X", "X"),
            (1, "X", "X"),
            (0, "Z", "Z"),
        ],
    )

    summary = backend.qiskit_summary()
    assert bits == (0, 1, 0, 1, 0)
    assert summary["circuit_count"] == 5
    assert len(backend.last_circuits) == 2
    assert len(backend.last_counts) == 2
    assert summary["counts_sample"] == [{"0": 1}, {"1": 1}]
    assert sum(summary["counts_by_outcome"].values()) == 5


def test_bb84_result_exports_qiskit_execution_summary() -> None:
    scenario = Scenario(pulses=4, clock_rate_hz=1_000_000.0, seed=17)
    backend = QiskitSamplerBackend(seed=17)

    result = BB84Protocol().run(scenario, backend=backend)
    payload = result.to_dict()

    assert payload["qiskit"]["backend"] == "QiskitSamplerBackend"
    assert payload["qiskit"]["primitive"] == "StatevectorSampler"
    assert payload["qiskit"]["shots_per_circuit"] == 1
    assert payload["qiskit"]["circuit_count"] == scenario.pulses
    assert payload["qiskit"]["counts_sample"] == backend.last_counts
    assert payload["qiskit"]["circuit_metadata_sample"][0]["protocol"] == "BB84"
    assert "e91_noiseless_sampler" not in payload["qiskit"]
    assert SimulationResult.from_json(result.to_json()).qiskit == result.qiskit


def test_configuring_backend_for_new_scenario_resets_execution_summary() -> None:
    backend = QiskitSamplerBackend(seed=17, max_recorded_results=0)
    protocol = BB84Protocol()
    first = Scenario(pulses=2, clock_rate_hz=1_000_000.0, seed=17)
    second = Scenario(pulses=3, clock_rate_hz=1_000_000.0, seed=18)

    first_result = protocol.run(first, backend=backend)
    second_result = protocol.run(second, backend=backend)

    assert first_result.qiskit["circuit_count"] == 2
    assert second_result.qiskit["circuit_count"] == 3
    assert sum(second_result.qiskit["counts_by_outcome"].values()) == 3
