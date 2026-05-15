# Parameters

Configuration fields include units in their names when units matter. Phase 3
uses the source, channel, and detector fields in BB84 execution through the
event layer. Phase 3.5 adds explicit timing fields in the same event layer.

## Scenario

- `pulses`: number of attempted protocol rounds. Must be positive.
- `clock_rate_hz`: pulse clock rate in hertz. Used to convert counters into
  rates.
- `seed`: central deterministic seed for protocol sampling.
- `event_sample_size`: number of events to keep when `store_full_event_log` is
  false.
- `store_full_event_log`: when true, store every event in `SimulationResult`;
  when false, store only the first `event_sample_size` events.

Derived duration:

```text
duration_s = pulses / clock_rate_hz
```

## Source

- `emission_probability`: probability that the source emits in a round.
- `mean_photon_number`: mean photon number for weak coherent or decoy-style
  sources. It may be `0.0` for vacuum decoy classes.
- `preparation_error_probability`: future state-preparation error probability.

Phase 3 models only the ideal single-photon source case. Each emitted pulse has
`photon_number=1`; a non-emitted pulse has `photon_number=0` and can still
produce a detector click through dark counts.

## Channel

- `distance_km`: channel distance in kilometers.
- `attenuation_db_km`: fiber attenuation in dB per kilometer.
- `fixed_loss_db`: extra fixed optical loss in dB.
- `depolarizing_probability`: future Qiskit/Aer state-noise parameter.
- `phase_damping_probability`: future Qiskit/Aer state-noise parameter.

Fiber physical-loss formula:

```text
loss_db = attenuation_db_km * distance_km + fixed_loss_db
eta_channel = 10 ** (-loss_db / 10)
```

For each emitted photon:

```text
transmitted = rng.random() < eta_channel
```

Photon loss is represented as an event-level no-click opportunity. It is not
modeled with Qiskit `amplitude_damping`, because fiber loss removes the photon
from the detected event stream rather than relaxing a computational qubit from
`|1>` to `|0>`.

## Detector

- `efficiency`: detector efficiency as a probability.
- `dark_count_rate_hz`: dark-count rate in hertz.
- `gate_width_s`: detection gate width in seconds.
- `readout_error_probability`: future readout-error probability.
- `double_click_policy`: `discard`, `random`, or `error`.
- `dead_time_s`: time after a detection during which the detector is
  unavailable.
- `afterpulse_probability`: per-gate probability of a false click after a
  previous detection.

Dark-count approximation:

```text
p_dark = 1 - exp(-dark_count_rate_hz * gate_width_s)
```

Phase 3.5 detector behavior:

- If no signal arrives and no dark count occurs, the event is not detected.
- If no signal arrives and a dark count occurs, Bob receives a random bit with
  `detection_origin="dark"`.
- If a signal arrives and the detector clicks from the signal, Bob receives the
  measured bit with `detection_origin="signal"`.
- If a signal click and dark count coincide, `double_click_policy` resolves the
  event:
  - `discard`: no detection is recorded and `detection_pattern` marks the
    discarded double click.
  - `random`: a random Bob bit is recorded.
  - `error`: the bit opposite to the measured signal bit is recorded when that
      bit is available.
- If a potential click occurs before the detector's `available_at` time, the
  event is discarded with `timing_status="dead_time"`.
- If no signal or dark click occurs after a previous detection,
  `afterpulse_probability` can create a false random-bit click with
  `detection_origin="afterpulse"`.

Detector efficiency is sampled before dark-count resolution:

```text
signal_click = signal_present and rng.random() < efficiency
```

The detector currently does not apply `readout_error_probability`; that remains
for a later Qiskit/Aer or detector-readout phase.

## Timing

Phase 3.5 makes slot synchronization explicit. A pulse attempted by Alice in
slot `n` is represented by `Event.time_slot == n`; `Event.index` is retained as
a compatible name for the same shared slot. Neither field is a received-photon
sequence number.

`TimingConfig` defines:

- `propagation_delay_s`: baseline flight time between Alice and Bob.
- `jitter_std_s`: standard deviation of arrival-time noise.
- `clock_offset_s`: fixed offset of Bob's detection clock relative to Alice.
- `clock_drift_ppm`: slow drift of Bob's clock over the run.
- `slot_assignment_policy`: how to handle signal arrivals outside the expected
  window. The default is `discard`; `nearest` explicitly assigns to the nearest
  Bob slot.

Bob's gate for slot `n` is centered at:

```text
gate_center_s =
  propagation_delay_s
  + clock_offset_s
  + n * (1 / clock_rate_hz) * (1 + clock_drift_ppm * 1e-6)
```

`bob_gate_start_s` and `bob_gate_end_s` are derived by subtracting and adding
half of `gate_width_s`.

With those parameters, an event distinguishes:

```text
time_slot = 4
arrival_time_s = expected_slot_4_time + jitter
bob_gate = 4
assigned_slot = 4 | 5 | None
timing_status = in_gate | early | late | ambiguous | dead_time
```

Lost photons should still produce no signal click. A dark count should still be
attached to the Bob gate in which it occurs. Timing fields decide whether a
signal can legitimately be measured in a gate; they do not shift later slots to
fill a loss.

## Post-Processing

- `qber_abort_threshold`: abort when QBER is greater than this value. Set to
  `None` to disable the abort threshold.
- `error_correction_efficiency`: `f_ec` in the simplified asymptotic BB84
  secret-fraction formula. Must be at least `1.0`.
- `sifting_enabled`: retained for validated configuration; Phase 3 BB84 always
  applies basis sifting.
- `privacy_amplification_enabled`: retained for future explicit privacy
  amplification steps.

Future Phase 3.6 post-processing parameters should make the simplified
key-rate estimate more concrete:

- `qber_sample_fraction`: fraction of sifted bits revealed publicly for QBER
  estimation.
- `qber_sample_seed`: optional seed offset or domain separator for selecting
  the revealed sample reproducibly.
- `reconciliation_method`: for example `block_parity` for a pedagogical
  parity-search protocol.
- `reconciliation_block_size`: block size used when comparing parities.
- `reconciliation_passes`: number of parity passes or permutations.
- `leak_ec`: measured or estimated public information revealed during error
  correction.
- `privacy_hash`: hash family used for pedagogical privacy amplification.
- `final_key_length`: target output length after privacy amplification.

The expected Phase 3.6 flow is:

```text
sifted_alice_bits, sifted_bob_bits
  -> reveal reproducible QBER sample
  -> abort if estimated_qber > qber_abort_threshold
  -> reconcile remaining bits
  -> account leak_ec
  -> privacy_amplify(corrected_key, final_key_length)
```

Error correction is meaningful only when Alice and Bob's sifted strings are
already correlated. If dark counts dominate and QBER approaches `0.5`, the run
should abort instead of attempting to force a shared key from random strings.

QBER:

```text
qber = errors / sifted        if sifted > 0
qber = 0                     if sifted == 0
```

Pedagogical BB84 secret fraction:

```text
h2(q) = -q log2(q) - (1 - q) log2(1 - q)
secret_fraction = max(0, 1 - f_ec * h2(qber) - h2(qber))
```

Rates:

```text
gain = detected / pulses
raw_detection_rate_hz = gain * clock_rate_hz
sifted_key_rate_bps = (sifted / pulses) * clock_rate_hz
secret_key_rate_bps = sifted_key_rate_bps * secret_fraction
```

If the abort threshold is enabled and exceeded, Phase 3 reports
`secret_key_rate_bps=0.0`.

In Phase 3, `loss_db` is the active channel loss for the scenario. `gain`
continues to mean detections per attempted pulse, including dark-count
detections.
