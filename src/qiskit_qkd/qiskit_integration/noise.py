"""Qiskit Aer noise-model adapters for detectable quantum-state noise."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qiskit_qkd._json import JSONObject
from qiskit_qkd.config import Scenario

QUANTUM_CHANNEL_OPERATIONS = ("id",)
READOUT_OPERATIONS = ("measure",)
EVENT_LAYER_EXCLUSIONS = (
    "fiber_loss_no_click",
    "detector_efficiency",
    "dark_counts",
    "dead_time",
    "afterpulsing",
    "timing_gates",
)


@dataclass(frozen=True, slots=True)
class AerNoiseModelAdapter:
    """Translate scenario state/readout noise into a Qiskit Aer `NoiseModel`.

    The adapter intentionally excludes photonic loss, no-clicks, detector
    efficiency, dark counts, dead time, afterpulsing, and timing gates. Those
    effects remain in the QKD event layer.
    """

    noise_model: Any
    components: tuple[str, ...] = ()
    parameters: JSONObject | None = None
    quantum_error_operations: tuple[str, ...] = ()
    readout_error_operations: tuple[str, ...] = ()

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> AerNoiseModelAdapter:
        """Build an Aer noise model for quantum-state and readout effects."""

        try:
            from qiskit_aer.noise import (  # type: ignore[import-not-found]
                NoiseModel,
                ReadoutError,
                depolarizing_error,
                phase_damping_error,
            )
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ImportError(
                "Qiskit Aer is required for AerNoiseModelAdapter. "
                "Install qiskit-qkd with the 'aer' extra.",
            ) from exc

        noise_model = NoiseModel()
        components: list[str] = []
        parameters: JSONObject = {}
        quantum_error: Any | None = None

        depolarizing_probability = scenario.channel.depolarizing_probability
        if depolarizing_probability > 0.0:
            quantum_error = depolarizing_error(depolarizing_probability, 1)
            components.append("channel_depolarizing")
            parameters["depolarizing_probability"] = depolarizing_probability

        phase_damping_probability = scenario.channel.phase_damping_probability
        if phase_damping_probability > 0.0:
            phase_error = phase_damping_error(phase_damping_probability)
            quantum_error = (
                phase_error
                if quantum_error is None
                else quantum_error.compose(phase_error)
            )
            components.append("channel_phase_damping")
            parameters["phase_damping_probability"] = phase_damping_probability

        quantum_error_operations: tuple[str, ...] = ()
        if quantum_error is not None:
            noise_model.add_all_qubit_quantum_error(
                quantum_error,
                list(QUANTUM_CHANNEL_OPERATIONS),
            )
            quantum_error_operations = QUANTUM_CHANNEL_OPERATIONS

        readout_error_probability = scenario.detector.readout_error_probability
        readout_error_operations: tuple[str, ...] = ()
        if readout_error_probability > 0.0:
            p = readout_error_probability
            noise_model.add_all_qubit_readout_error(
                ReadoutError([[1.0 - p, p], [p, 1.0 - p]]),
            )
            components.append("detector_readout")
            parameters["readout_error_probability"] = readout_error_probability
            readout_error_operations = READOUT_OPERATIONS

        return cls(
            noise_model=noise_model,
            components=tuple(components),
            parameters=parameters,
            quantum_error_operations=quantum_error_operations,
            readout_error_operations=readout_error_operations,
        )

    def summary(self) -> JSONObject:
        """Return a compact JSON-safe description of the Aer noise boundary."""

        return {
            "enabled": bool(self.components),
            "components": list(self.components),
            "parameters": dict(self.parameters or {}),
            "quantum_error_operations": list(self.quantum_error_operations),
            "readout_error_operations": list(self.readout_error_operations),
            "basis_gates": list(getattr(self.noise_model, "basis_gates", [])),
            "event_layer_exclusions": list(EVENT_LAYER_EXCLUSIONS),
        }
