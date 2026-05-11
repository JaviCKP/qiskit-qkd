import pytest
from qiskit import QuantumCircuit

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
    assert SimulationResult.from_json(result.to_json()).qiskit == result.qiskit
