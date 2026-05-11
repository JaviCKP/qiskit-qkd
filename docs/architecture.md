# Architecture

`qiskit-qkd` is Qiskit-first, not Qiskit-only. Qiskit owns the quantum circuit
path; the library owns the QKD event and post-processing path.

## Qiskit Layer

Use Qiskit for phenomena that are naturally represented as circuits or
primitives:

- `QuantumCircuit` objects for BB84 state preparation and measurement.
- Basis changes such as applying `H` before X-basis measurement.
- Primitive execution through current Sampler V2-style result objects.
- Future Aer `NoiseModel` integration for quantum state noise and readout
  error.
- Future transpilation, pass-manager, target, and circuit visualization
  workflows.

Phase 2 implements this layer with `CircuitFactory.bb84_prepare_measure()` and
`QiskitSamplerBackend`. The backend executes circuits in bounded primitive
batches, extracts primitive counts with `result[0].data.c.get_counts()`, and
keeps a JSON-safe execution summary on `SimulationResult.qiskit`.

## QKD Event Layer

Keep QKD-specific classical and photonic behavior outside Qiskit:

- Emission events and photon-number metadata.
- Channel loss as transmission/no-click events.
- Detector efficiency, dark counts, background counts, double clicks, dead
  time, jitter, and afterpulsing.
- Eve models and attack annotations.
- Sifting, QBER estimation, abort decisions, and key-rate formulas.
- `Event`, `Metrics`, and `SimulationResult` serialization.

Phase 2 uses ideal source/channel/detector assumptions: every pulse is emitted,
transmitted, detected, and marked with `detection_origin="signal"`. Later phases
can add physical loss and detector behavior without turning them into gates.

## Data Flow

1. `Scenario` stores validated parameters and the central seed.
2. `BB84Protocol` samples Alice bits, Alice bases, and Bob bases from that seed.
3. `CircuitFactory` builds a one-qubit BB84 circuit for each pulse.
4. `QiskitSamplerBackend` runs the circuit and returns Bob's measured bit.
5. The protocol records an `Event` for each pulse.
6. `sift_bb84_events()` marks matching-basis events as sifted.
7. `Metrics` aggregates counters, QBER, gain, rates, and abort status.
8. `SimulationResult` returns metrics, provenance, Qiskit execution metadata,
   and the configured event sample.

This boundary keeps the demo honest: Qiskit performs the quantum measurement,
while the QKD library performs the protocol bookkeeping.
