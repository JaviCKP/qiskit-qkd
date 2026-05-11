"""Inspectable Qiskit circuits for QKD protocol primitives."""

from __future__ import annotations

from qiskit import QuantumCircuit

BB84_BASES = {"Z", "X"}


def _validate_bit(bit: int) -> int:
    if bit not in {0, 1}:
        raise ValueError("bit must be 0 or 1")
    return bit


def _validate_basis(name: str, basis: str) -> str:
    if basis not in BB84_BASES:
        raise ValueError(f"{name} must be Z or X")
    return basis


class CircuitFactory:
    """Factory for small, inspectable QKD circuits."""

    @staticmethod
    def bb84_prepare_measure(
        bit: int,
        alice_basis: str,
        bob_basis: str,
    ) -> QuantumCircuit:
        """Build a one-pulse BB84 prepare-and-measure circuit."""

        bit = _validate_bit(bit)
        alice_basis = _validate_basis("alice_basis", alice_basis)
        bob_basis = _validate_basis("bob_basis", bob_basis)

        circuit = QuantumCircuit(1, 1, name="bb84_prepare_measure")

        if bit == 1:
            circuit.x(0)
        if alice_basis == "X":
            circuit.h(0)
        if bob_basis == "X":
            circuit.h(0)

        circuit.measure(0, 0)
        circuit.metadata = {
            "protocol": "BB84",
            "bit": bit,
            "alice_bit": bit,
            "alice_basis": alice_basis,
            "bob_basis": bob_basis,
        }
        return circuit
