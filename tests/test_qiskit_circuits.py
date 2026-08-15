import math

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
        "channel_operation": "id",
    }
    assert circuit.count_ops()["id"] == 1


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
        (True, "Z", "Z"),
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


@pytest.mark.parametrize("basis", ["Z", "X"])
def test_bb84_preparation_bit_flip_models_source_preparation_error(
    basis: str,
) -> None:
    circuit = CircuitFactory.bb84_prepare_measure(
        0,
        basis,
        basis,
        preparation_bit_flip=True,
    )

    assert sample_single_bit(circuit) == 1
    assert circuit.metadata["alice_bit"] == 0
    assert circuit.metadata["prepared_bit"] == 1
    assert circuit.metadata["preparation_error"] is True


def test_bb84_channel_polarization_rotation_is_explicit_coherent_gate() -> None:
    circuit = CircuitFactory.bb84_prepare_measure(
        0,
        "Z",
        "Z",
        channel_rotation_y_rad=math.pi,
    )

    assert sample_single_bit(circuit) == 1
    assert circuit.count_ops()["ry"] == 1
    assert circuit.metadata["channel_rotation_y_rad"] == math.pi


def test_e91_bell_measure_returns_two_qubit_circuit() -> None:
    circuit = CircuitFactory.e91_bell_measure(
        bell_state="psi_minus",
        alice_angle_rad=0.0,
        bob_angle_rad=0.0,
    )

    assert isinstance(circuit, QuantumCircuit)
    assert circuit.num_qubits == 2
    assert circuit.num_clbits == 2
    assert circuit.metadata["protocol"] == "E91"
    assert circuit.metadata["bell_state"] == "psi_minus"
    assert circuit.metadata["alice_angle_rad"] == 0.0
    assert circuit.metadata["bob_angle_rad"] == 0.0
    assert circuit.count_ops()["id"] == 1


def test_e91_singlet_same_angle_is_anticorrelated() -> None:
    circuit = CircuitFactory.e91_bell_measure(
        bell_state="psi_minus",
        alice_angle_rad=0.0,
        bob_angle_rad=0.0,
    )

    result = StatevectorSampler(seed=123).run([circuit], shots=1).result()
    measured = next(iter(result[0].data.c.get_counts()))
    alice_bit = int(measured[-1])
    bob_bit = int(measured[-2])

    assert alice_bit ^ bob_bit == 1


def test_e91_source_pair_error_is_explicit_pauli_on_bob_qubit() -> None:
    circuit = CircuitFactory.e91_bell_measure(
        bell_state="psi_minus",
        alice_angle_rad=0.0,
        bob_angle_rad=0.0,
        source_pair_error="x",
    )

    result = StatevectorSampler(seed=123).run([circuit], shots=1).result()
    measured = next(iter(result[0].data.c.get_counts()))
    alice_bit = int(measured[-1])
    bob_bit = int(measured[-2])

    assert alice_bit == bob_bit
    assert circuit.metadata["source_pair_error"] == "x"
