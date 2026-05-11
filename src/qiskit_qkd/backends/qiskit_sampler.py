"""Minimal Qiskit primitive backend for BB84 measurements."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import qiskit
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import require_non_negative_int, require_positive_int
from qiskit_qkd.qiskit_integration import CircuitFactory


class QiskitSamplerBackend:
    """Execute BB84 circuits through a Qiskit Sampler V2 primitive."""

    def __init__(
        self,
        sampler: Any | None = None,
        *,
        seed: int | None = None,
        shots_per_circuit: int = 1,
        max_circuits_per_job: int = 256,
        max_recorded_results: int = 16,
    ) -> None:
        self.seed = None if seed is None else require_non_negative_int("seed", seed)
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
        self.sampler = sampler or StatevectorSampler(seed=self.seed)
        self.last_circuits: list[QuantumCircuit] = []
        self.last_counts: list[dict[str, int]] = []
        self.circuit_count = 0
        self.counts_by_outcome: dict[str, int] = {}

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
                CircuitFactory.bb84_prepare_measure(bit, alice_basis, bob_basis)
                for bit, alice_basis, bob_basis in batch
            ]
            if not circuits:
                continue
            job = self.sampler.run(circuits, shots=self.shots_per_circuit)
            result = job.result()
            for circuit, pub_result in zip(circuits, result, strict=True):
                counts = dict(pub_result.data.c.get_counts())
                self.circuit_count += 1
                self._add_counts(counts)
                if len(self.last_circuits) < self.max_recorded_results:
                    self.last_circuits.append(circuit)
                    self.last_counts.append(counts)
                measured_bits.append(self._bit_from_counts(counts))
        return tuple(measured_bits)

    def provenance(self) -> JSONObject:
        """Return JSON-safe execution provenance for simulation results."""

        provenance: JSONObject = {
            "backend": type(self).__name__,
            "primitive": type(self.sampler).__name__,
            "shots_per_circuit": self.shots_per_circuit,
            "max_circuits_per_job": self.max_circuits_per_job,
            "max_recorded_results": self.max_recorded_results,
            "qiskit_version": qiskit.__version__,
        }
        if self.seed is not None:
            provenance["backend_seed"] = self.seed
        return provenance

    def qiskit_summary(self, *, sample_size: int = 16) -> JSONObject:
        """Return a JSON-safe summary of the latest primitive execution."""

        summary = self.provenance()
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
            },
        )
        return summary

    @staticmethod
    def _bit_from_counts(counts: dict[str, int]) -> int:
        if not counts:
            raise ValueError("Sampler returned no counts")
        measured, _ = max(counts.items(), key=lambda item: (item[1], item[0]))
        if measured not in {"0", "1"}:
            raise ValueError(f"Expected single-bit counts, got {measured!r}")
        return int(measured)

    def _add_counts(self, counts: dict[str, int]) -> None:
        for outcome, count in counts.items():
            self.counts_by_outcome[outcome] = (
                self.counts_by_outcome.get(outcome, 0) + count
            )
