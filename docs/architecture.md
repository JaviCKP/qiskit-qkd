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

Phase 3 uses this layer through `CircuitFactory.bb84_prepare_measure()` and
`QiskitSamplerBackend`. The backend executes circuits in bounded primitive
batches, extracts primitive counts with `result[0].data.c.get_counts()`, and
keeps a JSON-safe execution summary on `SimulationResult.qiskit`.

BB84 now calls this backend only for pulses that were emitted by the source and
survived the physical channel. No circuit is executed for a source miss, a lost
photon, or a pure dark-count event.

## QKD Event Layer

Keep QKD-specific classical and photonic behavior outside Qiskit:

- Emission events and photon-number metadata.
- Channel loss as transmission/no-click events.
- Detector efficiency, dark counts, and double clicks.
- Timing gates, jitter, clock offset/drift, dead time, and afterpulsing.
- Eve models and attack annotations.
- Sifting, QBER estimation, abort decisions, and key-rate formulas.
- `Event`, `Metrics`, and `SimulationResult` serialization.

Phase 3 owns fiber attenuation and detector dark counts in this event layer.
Photon loss and dark counts are not Qiskit gates and are not represented with
`amplitude_damping`. Qiskit receives only the surviving signal rounds whose
state still needs quantum measurement.

## Phase 3.5: Timing And Gates

Phase 3.5 makes the timing layer explicit. Alice's attempted pulse with
`Event.time_slot == n` and the compatible `Event.index == n` is a shared
time-window identifier, not a counter of photons that Bob successfully
received. A lost photon leaves that slot as a no-click opportunity; it does not
shift later detections forward.

The event layer tracks which slot Alice attempted, when a photon would arrive
at Bob, which detection gate was open, and whether a click was assigned to the
intended slot, a neighboring slot through an explicit policy, or no valid slot.
Dark counts and afterpulses are assigned to the Bob window in which they occur.

The Phase 3.5 boundary stays outside Qiskit:

- Propagation delay, jitter, clock offset, and clock drift are timing metadata.
- Gate assignment and out-of-window clicks are event-layer decisions.
- Dead time and afterpulsing use detector state across rounds.
- Sifting should use what Bob can publicly announce: detected slots and bases,
  not hidden facts such as `transmitted=True`.

This keeps the model honest. Qiskit still measures the quantum state when a
signal is available, while the QKD event layer decides whether that measured
signal is visible to Bob in the expected detection window.

## Future Phase 3.6: Classical Reconciliation

Phase 3 computes a simplified secret-key rate from QBER, but it does not yet
construct corrected Alice/Bob keys. Phase 3.6 should add an explicit classical
post-processing layer after sifting:

1. Alice and Bob derive candidate sifted strings from the same detected
   same-basis slots.
2. A public, reproducible subset is revealed to estimate QBER.
3. If QBER is too high, the run aborts before trying to reconcile unrelated
   strings.
4. If QBER is acceptable, a pedagogical reconciliation protocol reveals parity
   or syndrome information and corrects Bob's candidate key.
5. The simulator accounts for the public leakage as `leak_ec`.
6. Privacy amplification compresses the corrected key to remove information
   revealed during error correction and estimated from QBER.

This phase is classical and should not call Qiskit. It should also distinguish
between what Alice and Bob can know through public messages and what the
simulator can inspect for validation. Hidden event fields such as
`detection_origin` may be useful for diagnostics, but the reconciliation
protocol must not depend on Bob knowing which individual clicks were dark
counts.

## Data Flow

1. `Scenario` stores validated parameters and the central seed.
2. `BB84Protocol` samples source emission, Alice bits, Alice bases, Bob bases,
   channel transmission, and timing jitter from that seed.
3. `CircuitFactory` builds a one-qubit BB84 circuit only for emitted and
   transmitted signal rounds.
4. `QiskitSamplerBackend` runs those circuits and returns Bob's measured signal
   bits.
5. `ThresholdDetector` applies efficiency, dark-count probability,
   double-click policy, dead time, and afterpulsing.
6. The protocol records an `Event` for each attempted pulse.
7. `sift_bb84_event()` marks detected matching-basis events as sifted.
8. `Metrics` aggregates counters, QBER, loss, gain, rates, and abort status.
9. `SimulationResult` returns metrics, provenance, Qiskit execution metadata,
   and the configured event sample.

This boundary keeps the demo honest: Qiskit performs the quantum measurement,
while the QKD library performs photonic event sampling, detector bookkeeping,
and classical post-processing.
