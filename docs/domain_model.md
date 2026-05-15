# Domain Model

The domain model defines the smallest useful data objects for QKD simulations.
The model uses dataclasses with explicit validation and JSON serialization.
Phase 3 adds BB84 execution with fiber channel loss, detector efficiency, dark
counts, and double-click handling on top of these objects. Phase 3.5 adds
explicit timing synchronization, detector dead time, and afterpulsing.
Explicit reconciliation/privacy amplification, Eve, E91, and decoy-state
behavior remain future work.

## Scenario

`Scenario` is the complete reproducible setup for one simulation run. It stores:

- `pulses`: number of attempted emissions.
- `clock_rate_hz`: source clock rate.
- `seed`: central seed used to create deterministic random generators.
- `protocol`, `source`, `channel`, `detector`, `timing`, and
  `post_processing` configs.
- `event_sample_size`: maximum sampled event records to keep.
- `store_full_event_log`: disabled by default to avoid storing millions of rows.
- `metadata`: JSON-safe extra labels.

The same scenario and seed produce the same digest and reproducibility summary.

## Config Objects

The initial config objects are intentionally small:

- `ProtocolConfig`: protocol name and basis choices.
- `SourceConfig`: source kind, emission probability, mean photon number, and
  preparation error probability.
- `ChannelConfig`: channel kind, `distance_km`, `attenuation_db_km`,
  `fixed_loss_db`, depolarizing probability, and phase damping probability.
- `DetectorConfig`: detector kind, efficiency, `dark_count_rate_hz`,
  `gate_width_s`, `dead_time_s`, `afterpulse_probability`, readout error
  probability, and double-click policy.
- `TimingConfig`: propagation delay, jitter, Bob clock offset/drift, and slot
  assignment policy.
- `PostProcessingConfig`: sifting flag, QBER abort threshold, error correction
  efficiency, and privacy amplification flag.

Values are checked at construction time. Probabilities must be in `[0, 1]`,
rates and distances must be non-negative, and time windows must be positive.

## Results

`Event` represents one sampled protocol round. It contains trace fields for
Alice and Bob bases, emission, timing, transmission, detection, sifting,
errors, decoy intensity, Eve action/basis markers, and optional tags.

`Event.index` is retained for compatibility, and `Event.time_slot` makes the
meaning explicit: it is the shared Alice/Bob clock slot. It is not a
received-photon counter. Timing fields include `emission_time_s`,
`expected_arrival_time_s`, `arrival_time_s`, `bob_gate_start_s`,
`bob_gate_end_s`, `assigned_slot`, and `timing_status`.

`Metrics` stores aggregate counters and rates:

- pulses, emitted, transmitted, detected, sifted, and errors.
- timing discards, dead-time discards, and afterpulse clicks.
- QBER, loss, gain, raw detection rate, sifted key rate, and secret key rate.
- abort flag, Eve summary fields, and optional CHSH value.

Future Phase 3.6 should add post-processing diagnostics such as QBER sample
size, revealed sample count, `leak_ec`, corrected-key length, residual mismatch
count, privacy-amplified length, and final-key digest for reproducible small
examples.

`SimulationResult` stores the scenario, metrics, provenance, Qiskit execution
summary, library version, and an optional event sample. Provenance includes the
seed, scenario digest, library version, and RNG family. The Qiskit summary is
JSON-safe and stores counts, circuit metadata samples, primitive name, and
execution sizing rather than raw `QuantumCircuit` objects.

## JSON

Every public model supports `to_dict` and `from_dict`. `Scenario` and
`SimulationResult` also support `to_json` and `from_json`.

```python
from qiskit_qkd import Metrics, Scenario, SimulationResult

scenario = Scenario(pulses=1_000, clock_rate_hz=1_000_000.0, seed=7)
result = SimulationResult(
    scenario=scenario,
    metrics=Metrics(pulses=scenario.pulses),
)

payload = result.to_json()
restored = SimulationResult.from_json(payload)
assert restored.summary() == result.summary()
```
