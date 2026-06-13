"""Minimal Qiskit primitive backend for BB84 measurements."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

import qiskit
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
from qiskit.quantum_info import Statevector

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import (
    require_finite_number,
    require_non_negative_int,
    require_positive_int,
    require_probability,
)
from qiskit_qkd.qiskit_integration import CircuitFactory, TranspilationOptions
from qiskit_qkd.qiskit_integration.transpilation import (
    disabled_transpilation_summary,
)


def _qiskit_aer_version() -> str | None:
    try:
        import qiskit_aer  # type: ignore[import-not-found]
    except ImportError:
        return None
    return str(qiskit_aer.__version__)


def scenario_requires_aer_noise(scenario: Any) -> bool:
    """Return whether a scenario has Aer-level quantum/readout noise enabled."""

    return (
        scenario.channel.depolarizing_probability > 0.0
        or scenario.channel.phase_damping_probability > 0.0
        or scenario.detector.readout_error_probability > 0.0
    )


def backend_from_scenario(scenario: Any) -> QiskitSamplerBackend:
    """Build the default backend implied by scenario-level Qiskit noise fields."""

    if not scenario_requires_aer_noise(scenario):
        return QiskitSamplerBackend(seed=scenario.seed)

    from qiskit_qkd.qiskit_integration.noise import AerNoiseModelAdapter

    adapter = AerNoiseModelAdapter.from_scenario(scenario)
    return QiskitSamplerBackend(
        seed=scenario.seed,
        seed_simulator=scenario.seed,
        noise_model=adapter.noise_model,
        noise_summary=adapter.summary(),
    )


class QiskitSamplerBackend:
    """Execute BB84 circuits through a Qiskit Sampler V2 primitive."""

    def __init__(
        self,
        sampler: Any | None = None,
        *,
        seed: int | None = None,
        seed_simulator: int | None = None,
        shots_per_circuit: int = 1,
        max_circuits_per_job: int = 256,
        max_recorded_results: int = 16,
        noise_model: Any | None = None,
        noise_summary: Mapping[str, Any] | None = None,
        transpilation: TranspilationOptions | None = None,
        preparation_error_probability: float = 0.0,
        channel_rotation_y_rad: float = 0.0,
        channel_rotation_z_rad: float = 0.0,
    ) -> None:
        self.seed = None if seed is None else require_non_negative_int("seed", seed)
        self.seed_simulator = (
            None
            if seed_simulator is None
            else require_non_negative_int("seed_simulator", seed_simulator)
        )
        self.shots_per_circuit = require_positive_int(
            "shots_per_circuit",
            shots_per_circuit,
        )
        self.max_circuits_per_job = require_positive_int(
            "max_circuits_per_job",
            max_circuits_per_job,
        )
        self.max_recorded_results = require_non_negative_int(
            "max_recorded_results",
            max_recorded_results,
        )
        self.noise_model = noise_model
        self.noise_summary = dict(noise_summary) if noise_summary is not None else None
        self.transpilation = transpilation
        self.preparation_error_probability = require_probability(
            "preparation_error_probability",
            preparation_error_probability,
        )
        self.channel_rotation_y_rad = require_finite_number(
            "channel_rotation_y_rad",
            channel_rotation_y_rad,
        )
        self.channel_rotation_z_rad = require_finite_number(
            "channel_rotation_z_rad",
            channel_rotation_z_rad,
        )
        self._preparation_rng = random.Random(
            None if self.seed is None else self.seed + 0x51A7E,
        )
        self._measurement_rng = random.Random(
            None if self.seed is None else self.seed + 0xE91,
        )
        self._transpilation_backend: Any | None = None
        self._sampler_provided = sampler is not None
        self.sampler = sampler or self._default_sampler()
        self.reset_execution_summary()

    def reset_execution_summary(self) -> None:
        """Clear per-run execution artifacts and counters."""

        self.last_circuits: list[QuantumCircuit] = []
        self.last_counts: list[dict[str, int]] = []
        self.circuit_count = 0
        self.counts_by_outcome: dict[str, int] = {}
        self.e91_distribution_shots_per_circuit: int | None = None
        self.e91_noiseless_statevector_used = False
        self.bb84_noiseless_statevector_used = False
        self._effective_transpilation: TranspilationOptions | None = None

    def measure_bb84(self, bit: int, alice_basis: str, bob_basis: str) -> int:
        """Measure one BB84 pulse and return Bob's classical bit."""

        return self.measure_bb84_batch([(bit, alice_basis, bob_basis)])[0]

    def measure_bb84_batch(
        self,
        rounds: Sequence[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        """Measure BB84 pulses in primitive jobs and return Bob's bits in order."""

        measured_bits: list[int] = []
        for start in range(0, len(rounds), self.max_circuits_per_job):
            batch = rounds[start : start + self.max_circuits_per_job]
            circuits = [
                CircuitFactory.bb84_prepare_measure(
                    bit,
                    alice_basis,
                    bob_basis,
                    preparation_bit_flip=self._sample_preparation_error(),
                    channel_rotation_y_rad=self.channel_rotation_y_rad,
                    channel_rotation_z_rad=self.channel_rotation_z_rad,
                )
                for bit, alice_basis, bob_basis in batch
            ]
            if not circuits:
                continue
            circuits = self._prepare_circuits(circuits)
            if self._can_sample_noiseless_statevector():
                for circuit in circuits:
                    counts = self._sample_bb84_statevector_counts(circuit)
                    self.bb84_noiseless_statevector_used = True
                    self._record_execution(circuit, counts)
                    measured_bits.append(self._bit_from_counts(counts))
                continue
            job = self.sampler.run(circuits, shots=self.shots_per_circuit)
            result = job.result()
            for circuit, pub_result in zip(circuits, result, strict=True):
                counts = dict(pub_result.data.c.get_counts())
                self._record_execution(circuit, counts)
                measured_bits.append(self._sample_bit_from_counts(counts))
        return tuple(measured_bits)

    def measure_e91_batch(
        self,
        rounds: Sequence[tuple[float, float, str]],
    ) -> tuple[tuple[int, int], ...]:
        """Measure E91 Bell pairs and return Alice/Bob bits in order."""

        measured_pairs: list[tuple[int, int]] = []
        for start in range(0, len(rounds), self.max_circuits_per_job):
            batch = rounds[start : start + self.max_circuits_per_job]
            circuits = [
                CircuitFactory.e91_bell_measure(
                    bell_state=bell_state,
                    alice_angle_rad=alice_angle_rad,
                    bob_angle_rad=bob_angle_rad,
                    source_pair_error=self._sample_source_pair_error(),
                    channel_rotation_y_rad=self.channel_rotation_y_rad,
                    channel_rotation_z_rad=self.channel_rotation_z_rad,
                )
                for alice_angle_rad, bob_angle_rad, bell_state in batch
            ]
            if not circuits:
                continue
            circuits = self._prepare_circuits(circuits)
            if self._can_sample_noiseless_statevector():
                for circuit in circuits:
                    counts = self._sample_e91_statevector_counts(circuit)
                    self.e91_noiseless_statevector_used = True
                    self._record_execution(circuit, counts)
                    measured_pairs.append(self._bit_pair_from_counts(counts))
                continue
            e91_shots = max(self.shots_per_circuit, 64)
            self.e91_distribution_shots_per_circuit = e91_shots
            job = self.sampler.run(circuits, shots=e91_shots)
            result = job.result()
            for circuit, pub_result in zip(circuits, result, strict=True):
                counts = dict(pub_result.data.c.get_counts())
                self._record_execution(circuit, counts)
                measured_pairs.append(self._sample_bit_pair_from_counts(counts))
        return tuple(measured_pairs)

    def provenance(self) -> JSONObject:
        """Return JSON-safe execution provenance for simulation results."""

        provenance: JSONObject = {
            "backend": type(self).__name__,
            "primitive": type(self.sampler).__name__,
            "shots_per_circuit": self.shots_per_circuit,
            "max_circuits_per_job": self.max_circuits_per_job,
            "max_recorded_results": self.max_recorded_results,
            "qiskit_version": qiskit.__version__,
            "qiskit_aer_version": _qiskit_aer_version(),
        }
        if self.seed is not None:
            provenance["backend_seed"] = self.seed
        if self.seed_simulator is not None:
            provenance["seed_simulator"] = self.seed_simulator
        return provenance

    def configure_from_scenario(self, scenario: Any) -> None:
        """Bind scenario-level source/channel quantum imperfections."""

        self.reset_execution_summary()
        self.preparation_error_probability = require_probability(
            "preparation_error_probability",
            scenario.source.preparation_error_probability,
        )
        self.channel_rotation_y_rad = require_finite_number(
            "channel_rotation_y_rad",
            scenario.channel.polarization_rotation_y_rad,
        )
        self.channel_rotation_z_rad = require_finite_number(
            "channel_rotation_z_rad",
            scenario.channel.polarization_rotation_z_rad,
        )
        self._preparation_rng = random.Random(scenario.seed + 0x51A7E)
        self._measurement_rng = random.Random(scenario.seed + 0xE91)

    def qiskit_summary(self, *, sample_size: int = 16) -> JSONObject:
        """Return a JSON-safe summary of the latest primitive execution."""

        summary = self.provenance()
        transpilation = self._transpilation_summary()
        summary.update(
            {
                "circuit_count": self.circuit_count,
                "recorded_circuit_count": len(self.last_circuits),
                "counts_sample": self.last_counts[:sample_size],
                "circuit_metadata_sample": [
                    dict(circuit.metadata or {})
                    for circuit in self.last_circuits[:sample_size]
                ],
                "counts_by_outcome": dict(self.counts_by_outcome),
                "noise_model": self._noise_model_summary(),
                "transpilation": transpilation,
            },
        )
        if self.e91_distribution_shots_per_circuit is not None:
            summary["e91_distribution_shots_per_circuit"] = (
                self.e91_distribution_shots_per_circuit
            )
        if self.e91_noiseless_statevector_used:
            summary["e91_noiseless_sampler"] = "Statevector"
        if self.bb84_noiseless_statevector_used:
            summary["bb84_noiseless_sampler"] = "Statevector"
        return summary

    def _default_sampler(self) -> Any:
        if self.noise_model is None:
            return StatevectorSampler(seed=self.seed)
        try:
            from qiskit_aer import AerSimulator  # type: ignore[import-not-found]
            from qiskit_aer.primitives import (  # type: ignore[import-not-found]
                SamplerV2,
            )
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ImportError(
                "Qiskit Aer is required when noise_model is provided.",
            ) from exc

        backend_options: dict[str, Any] = {"noise_model": self.noise_model}
        if self.seed_simulator is not None:
            backend_options["seed_simulator"] = self.seed_simulator
        self._transpilation_backend = AerSimulator(noise_model=self.noise_model)
        return SamplerV2(
            seed=self.seed_simulator if self.seed_simulator is not None else self.seed,
            options={"backend_options": backend_options},
        )

    def _prepare_circuits(
        self,
        circuits: Sequence[QuantumCircuit],
    ) -> list[QuantumCircuit]:
        if self.transpilation is None:
            return list(circuits)
        transpilation = self._transpilation_for_circuits(circuits)
        self._effective_transpilation = transpilation
        return transpilation.run(
            circuits,
            backend=self._transpilation_backend,
        )

    def _transpilation_for_circuits(
        self,
        circuits: Sequence[QuantumCircuit],
    ) -> TranspilationOptions:
        if (
            self._channel_marker_noise_enabled()
            and self.transpilation is not None
            and self.transpilation.optimization_level > 0
            and any(circuit.count_ops().get("id", 0) > 0 for circuit in circuits)
        ):
            return replace(self.transpilation, optimization_level=0)
        if self.transpilation is None:
            raise ValueError("transpilation options are not configured")
        return self.transpilation

    def _channel_marker_noise_enabled(self) -> bool:
        if self.noise_model is None:
            return False
        if self.noise_summary is None:
            return True
        if "quantum_error_operations" not in self.noise_summary:
            return True
        operations = self.noise_summary["quantum_error_operations"]
        return "id" in operations

    def _transpilation_summary(self) -> JSONObject:
        active = (
            self._effective_transpilation
            if self._effective_transpilation is not None
            else self.transpilation
        )
        if active is None:
            return disabled_transpilation_summary()
        summary = active.to_dict()
        if (
            self.transpilation is not None
            and active.optimization_level != self.transpilation.optimization_level
        ):
            summary["requested_optimization_level"] = (
                self.transpilation.optimization_level
            )
            summary["adjustment"] = "preserve_aer_channel_marker"
        return summary

    def _noise_model_summary(self) -> JSONObject:
        if self.noise_summary is not None:
            return dict(self.noise_summary)
        if self.noise_model is None:
            return {"enabled": False, "components": []}
        return {
            "enabled": True,
            "components": ["external_noise_model"],
            "basis_gates": list(getattr(self.noise_model, "basis_gates", [])),
        }

    def _sample_preparation_error(self) -> bool:
        return (
            self.preparation_error_probability > 0.0
            and self._preparation_rng.random() < self.preparation_error_probability
        )

    def _sample_source_pair_error(self) -> str | None:
        if (
            self.preparation_error_probability == 0.0
            or self._preparation_rng.random() >= self.preparation_error_probability
        ):
            return None
        return self._preparation_rng.choice(("x", "y", "z"))

    @staticmethod
    def _bit_from_counts(counts: dict[str, int]) -> int:
        if not counts:
            raise ValueError("Sampler returned no counts")
        measured, _ = max(counts.items(), key=lambda item: (item[1], item[0]))
        if measured not in {"0", "1"}:
            raise ValueError(f"Expected single-bit counts, got {measured!r}")
        return int(measured)

    def _sample_bit_from_counts(self, counts: dict[str, int]) -> int:
        if not counts:
            raise ValueError("Sampler returned no counts")
        total = sum(counts.values())
        sample = self._measurement_rng.randrange(total)
        cumulative = 0
        for measured, count in sorted(counts.items()):
            if measured not in {"0", "1"}:
                raise ValueError(f"Expected single-bit counts, got {measured!r}")
            cumulative += count
            if sample < cumulative:
                return int(measured)
        raise ValueError("Sampler counts could not be sampled")

    def _add_counts(self, counts: dict[str, int]) -> None:
        for outcome, count in counts.items():
            self.counts_by_outcome[outcome] = (
                self.counts_by_outcome.get(outcome, 0) + count
            )

    def _record_execution(
        self,
        circuit: QuantumCircuit,
        counts: dict[str, int],
    ) -> None:
        self.circuit_count += 1
        self._add_counts(counts)
        if len(self.last_circuits) < self.max_recorded_results:
            self.last_circuits.append(circuit)
            self.last_counts.append(counts)

    @staticmethod
    def _bit_pair_from_counts(counts: dict[str, int]) -> tuple[int, int]:
        if not counts:
            raise ValueError("Sampler returned no counts")
        measured, _ = max(counts.items(), key=lambda item: (item[1], item[0]))
        if len(measured) != 2 or any(bit not in {"0", "1"} for bit in measured):
            raise ValueError(f"Expected two-bit counts, got {measured!r}")
        alice_bit = int(measured[-1])
        bob_bit = int(measured[-2])
        return alice_bit, bob_bit

    def _sample_bit_pair_from_counts(self, counts: dict[str, int]) -> tuple[int, int]:
        if not counts:
            raise ValueError("Sampler returned no counts")
        total = sum(counts.values())
        sample = self._measurement_rng.randrange(total)
        cumulative = 0
        for measured, count in sorted(counts.items()):
            if len(measured) != 2 or any(bit not in {"0", "1"} for bit in measured):
                raise ValueError(f"Expected two-bit counts, got {measured!r}")
            cumulative += count
            if sample < cumulative:
                alice_bit = int(measured[-1])
                bob_bit = int(measured[-2])
                return alice_bit, bob_bit
        raise ValueError("Sampler counts could not be sampled")

    def _can_sample_noiseless_statevector(self) -> bool:
        return (
            not self._sampler_provided
            and self.noise_model is None
            and self.transpilation is None
        )

    def _sample_bb84_statevector_counts(
        self,
        circuit: QuantumCircuit,
    ) -> dict[str, int]:
        unitary = circuit.remove_final_measurements(inplace=False)
        probabilities = Statevector.from_instruction(unitary).probabilities_dict()
        sample = self._measurement_rng.random()
        cumulative = 0.0
        for outcome, probability in sorted(probabilities.items()):
            if outcome not in {"0", "1"}:
                raise ValueError(
                    f"Expected single-bit statevector outcome, got {outcome!r}",
                )
            cumulative += probability
            if sample < cumulative:
                return {outcome: 1}
        outcome = sorted(probabilities)[-1]
        return {outcome: 1}

    def _sample_e91_statevector_counts(
        self,
        circuit: QuantumCircuit,
    ) -> dict[str, int]:
        unitary = circuit.remove_final_measurements(inplace=False)
        probabilities = Statevector.from_instruction(unitary).probabilities_dict()
        sample = self._measurement_rng.random()
        cumulative = 0.0
        for outcome, probability in sorted(probabilities.items()):
            if len(outcome) != 2 or any(bit not in {"0", "1"} for bit in outcome):
                raise ValueError(
                    f"Expected two-bit statevector outcome, got {outcome!r}",
                )
            cumulative += probability
            if sample < cumulative:
                return {outcome: 1}
        outcome = sorted(probabilities)[-1]
        return {outcome: 1}
