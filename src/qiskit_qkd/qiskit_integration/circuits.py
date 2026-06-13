"""Inspectable Qiskit circuits for QKD protocol primitives."""

from __future__ import annotations

from qiskit import QuantumCircuit

from qiskit_qkd._validation import require_bool, require_finite_number

BB84_BASES = {"Z", "X"}
E91_BELL_STATES = {"psi_minus", "phi_plus"}
E91_SOURCE_PAIR_ERRORS = {"x", "y", "z"}


def _validate_bit(bit: int) -> int:
    if not isinstance(bit, int) or isinstance(bit, bool) or bit not in {0, 1}:
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
        *,
        preparation_bit_flip: bool = False,
        channel_rotation_y_rad: float = 0.0,
        channel_rotation_z_rad: float = 0.0,
    ) -> QuantumCircuit:
        """Build a one-pulse BB84 prepare-and-measure circuit."""

        bit = _validate_bit(bit)
        alice_basis = _validate_basis("alice_basis", alice_basis)
        bob_basis = _validate_basis("bob_basis", bob_basis)
        preparation_bit_flip = require_bool(
            "preparation_bit_flip",
            preparation_bit_flip,
        )
        channel_rotation_y_rad = require_finite_number(
            "channel_rotation_y_rad",
            channel_rotation_y_rad,
        )
        channel_rotation_z_rad = require_finite_number(
            "channel_rotation_z_rad",
            channel_rotation_z_rad,
        )
        prepared_bit = 1 - bit if preparation_bit_flip else bit

        circuit = QuantumCircuit(1, 1, name="bb84_prepare_measure")

        if prepared_bit == 1:
            circuit.x(0)
        if alice_basis == "X":
            circuit.h(0)
        circuit.id(0)
        if channel_rotation_y_rad != 0.0:
            circuit.ry(channel_rotation_y_rad, 0)
        if channel_rotation_z_rad != 0.0:
            circuit.rz(channel_rotation_z_rad, 0)
        if bob_basis == "X":
            circuit.h(0)

        circuit.measure(0, 0)
        circuit.metadata = {
            "protocol": "BB84",
            "bit": bit,
            "alice_bit": bit,
            "alice_basis": alice_basis,
            "bob_basis": bob_basis,
            "channel_operation": "id",
        }
        if preparation_bit_flip:
            circuit.metadata["prepared_bit"] = prepared_bit
            circuit.metadata["preparation_error"] = True
        if channel_rotation_y_rad != 0.0:
            circuit.metadata["channel_rotation_y_rad"] = channel_rotation_y_rad
        if channel_rotation_z_rad != 0.0:
            circuit.metadata["channel_rotation_z_rad"] = channel_rotation_z_rad
        return circuit

    @staticmethod
    def e91_bell_measure(
        *,
        bell_state: str = "psi_minus",
        alice_angle_rad: float,
        bob_angle_rad: float,
        source_pair_error: str | None = None,
        channel_rotation_y_rad: float = 0.0,
        channel_rotation_z_rad: float = 0.0,
    ) -> QuantumCircuit:
        """Build a two-qubit E91 Bell-pair measurement circuit."""

        bell_state = bell_state.lower()
        if bell_state not in E91_BELL_STATES:
            raise ValueError("bell_state must be psi_minus or phi_plus")
        alice_angle_rad = require_finite_number(
            "alice_angle_rad",
            alice_angle_rad,
        )
        bob_angle_rad = require_finite_number("bob_angle_rad", bob_angle_rad)
        channel_rotation_y_rad = require_finite_number(
            "channel_rotation_y_rad",
            channel_rotation_y_rad,
        )
        channel_rotation_z_rad = require_finite_number(
            "channel_rotation_z_rad",
            channel_rotation_z_rad,
        )
        if source_pair_error is not None:
            source_pair_error = source_pair_error.lower()
            if source_pair_error not in E91_SOURCE_PAIR_ERRORS:
                raise ValueError("source_pair_error must be x, y, z, or None")

        circuit = QuantumCircuit(2, 2, name="e91_bell_measure")
        if bell_state == "phi_plus":
            circuit.h(0)
            circuit.cx(0, 1)
        else:
            circuit.h(0)
            circuit.x(1)
            circuit.cx(0, 1)
            circuit.z(0)

        if source_pair_error == "x":
            circuit.x(1)
        elif source_pair_error == "y":
            circuit.y(1)
        elif source_pair_error == "z":
            circuit.z(1)

        circuit.id(1)
        if channel_rotation_y_rad != 0.0:
            circuit.ry(channel_rotation_y_rad, 1)
        if channel_rotation_z_rad != 0.0:
            circuit.rz(channel_rotation_z_rad, 1)

        if alice_angle_rad != 0.0:
            circuit.ry(-alice_angle_rad, 0)
        if bob_angle_rad != 0.0:
            circuit.ry(-bob_angle_rad, 1)
        circuit.measure(0, 0)
        circuit.measure(1, 1)
        circuit.metadata = {
            "protocol": "E91",
            "bell_state": bell_state,
            "alice_angle_rad": alice_angle_rad,
            "bob_angle_rad": bob_angle_rad,
            "channel_operation": "id",
        }
        if source_pair_error is not None:
            circuit.metadata["source_pair_error"] = source_pair_error
        if channel_rotation_y_rad != 0.0:
            circuit.metadata["channel_rotation_y_rad"] = channel_rotation_y_rad
        if channel_rotation_z_rad != 0.0:
            circuit.metadata["channel_rotation_z_rad"] = channel_rotation_z_rad
        return circuit
