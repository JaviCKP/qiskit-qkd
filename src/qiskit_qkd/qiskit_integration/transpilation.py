"""Controlled Qiskit transpilation options for QKD circuits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from qiskit import QuantumCircuit, transpile
from qiskit.transpiler import generate_preset_pass_manager

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import require_non_negative_int


def _normalize_basis_gates(value: Sequence[str] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(str(gate) for gate in value)


@dataclass(frozen=True, slots=True)
class TranspilationOptions:
    """Small JSON-reportable wrapper around Qiskit's pass-manager flow."""

    optimization_level: int = 1
    seed_transpiler: int | None = None
    basis_gates: tuple[str, ...] | None = None
    backend: Any | None = None
    target: Any | None = None

    def __post_init__(self) -> None:
        level = require_non_negative_int(
            "optimization_level",
            self.optimization_level,
        )
        if level > 3:
            raise ValueError("optimization_level must be between 0 and 3")
        object.__setattr__(self, "optimization_level", level)
        if self.seed_transpiler is not None:
            object.__setattr__(
                self,
                "seed_transpiler",
                require_non_negative_int("seed_transpiler", self.seed_transpiler),
            )
        object.__setattr__(
            self,
            "basis_gates",
            _normalize_basis_gates(self.basis_gates),
        )

    def run(
        self,
        circuits: Sequence[QuantumCircuit],
        *,
        backend: Any | None = None,
    ) -> list[QuantumCircuit]:
        """Transpile circuits while preserving circuit metadata."""

        effective_backend = self.backend if self.backend is not None else backend
        if effective_backend is not None or self.target is not None:
            pass_manager = generate_preset_pass_manager(
                optimization_level=self.optimization_level,
                backend=effective_backend,
                target=self.target,
                basis_gates=list(self.basis_gates) if self.basis_gates else None,
                seed_transpiler=self.seed_transpiler,
            )
            transpiled = pass_manager.run(list(circuits))
            return list(transpiled) if isinstance(transpiled, list) else [transpiled]

        transpiled = transpile(
            list(circuits),
            optimization_level=self.optimization_level,
            basis_gates=list(self.basis_gates) if self.basis_gates else None,
            seed_transpiler=self.seed_transpiler,
        )
        return list(transpiled) if isinstance(transpiled, list) else [transpiled]

    def to_dict(self) -> JSONObject:
        """Return JSON-safe transpilation provenance."""

        return {
            "enabled": True,
            "optimization_level": self.optimization_level,
            "seed_transpiler": self.seed_transpiler,
            "basis_gates": list(self.basis_gates) if self.basis_gates else None,
            "backend": type(self.backend).__name__ if self.backend else None,
            "target": type(self.target).__name__ if self.target else None,
        }


def disabled_transpilation_summary() -> JSONObject:
    """Return the standard JSON-safe summary for no transpilation."""

    return {
        "enabled": False,
        "optimization_level": None,
        "seed_transpiler": None,
        "basis_gates": None,
        "backend": None,
        "target": None,
    }
