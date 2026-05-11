# Domain Model

The domain model defines the smallest useful data objects for QKD simulations.
The model uses dataclasses with explicit validation and JSON serialization.
Phase 2 adds ideal BB84 execution on top of these objects; physical channel
loss, detector noise, Eve, E91, and decoy-state behavior remain future work.

## Scenario

`Scenario` is the complete reproducible setup for one simulation run. It stores:

- `pulses`: number of attempted emissions.
- `clock_rate_hz`: source clock rate.
- `seed`: central seed used to create deterministic random generators.
- `protocol`, `source`, `channel`, `detector`, and `post_processing` configs.
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
  `gate_width_s`, readout error probability, and double-click policy.
- `PostProcessingConfig`: sifting flag, QBER abort threshold, error correction
  efficiency, and privacy amplification flag.

Values are checked at construction time. Probabilities must be in `[0, 1]`,
rates and distances must be non-negative, and time windows must be positive.

## Results

`Event` represents one sampled protocol round. It contains trace fields for
Alice and Bob bases, emission, transmission, detection, sifting, errors, decoy
intensity, Eve action/basis markers, and optional tags.

`Metrics` stores aggregate counters and rates:

- pulses, emitted, transmitted, detected, sifted, and errors.
- QBER, loss, gain, raw detection rate, sifted key rate, and secret key rate.
- abort flag, Eve summary fields, and optional CHSH value.

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
