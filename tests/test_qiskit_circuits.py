import pytest
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

from qiskit_qkd.qiskit_integration import CircuitFactory


def sample_single_bit(circuit: QuantumCircuit) -> int:
    result = StatevectorSampler(seed=123).run([circuit], shots=1).result()
    counts = result[0].data.c.get_counts()
    assert sum(counts.values()) == 1
    return int(next(iter(counts)))


def test_bb84_prepare_measure_returns_single_qubit_circuit() -> None:
    circuit = CircuitFactory.bb84_prepare_measure(0, "Z", "Z")

    assert isinstance(circuit, QuantumCircuit)
    assert circuit.num_qubits == 1
    assert circuit.num_clbits == 1
    assert circuit.metadata == {
        "protocol": "BB84",
        "bit": 0,
        "alice_bit": 0,
        "alice_basis": "Z",
        "bob_basis": "Z",
    }


@pytest.mark.parametrize("bit", [0, 1])
def test_bb84_z_basis_measurement_preserves_bit(bit: int) -> None:
    circuit = CircuitFactory.bb84_prepare_measure(bit, "Z", "Z")

    assert sample_single_bit(circuit) == bit


@pytest.mark.parametrize("bit", [0, 1])
def test_bb84_x_basis_measurement_preserves_bit(bit: int) -> None:
    circuit = CircuitFactory.bb84_prepare_measure(bit, "X", "X")

    assert sample_single_bit(circuit) == bit


@pytest.mark.parametrize(
    ("bit", "alice_basis", "bob_basis"),
    [
        (2, "Z", "Z"),
        (0, "Y", "Z"),
        (0, "Z", "Y"),
    ],
)
def test_bb84_prepare_measure_rejects_invalid_inputs(
    bit: int,
    alice_basis: str,
    bob_basis: str,
) -> None:
    with pytest.raises(ValueError):
        CircuitFactory.bb84_prepare_measure(bit, alice_basis, bob_basis)
