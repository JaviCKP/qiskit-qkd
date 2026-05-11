# Parameters

Configuration fields include units in their names when units matter. Phase 2
uses the ideal subset for BB84 execution and documents the remaining validated
fields for later physical models.

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

## Channel

- `distance_km`: channel distance in kilometers.
- `attenuation_db_km`: fiber attenuation in dB per kilometer.
- `fixed_loss_db`: extra fixed optical loss in dB.
- `depolarizing_probability`: future Qiskit/Aer state-noise parameter.
- `phase_damping_probability`: future Qiskit/Aer state-noise parameter.

Future physical-loss formula:

```text
loss_db = attenuation_db_km * distance_km + fixed_loss_db
eta_channel = 10 ** (-loss_db / 10)
```

Phase 2 keeps `loss_db=0.0` because the implemented BB84 path is ideal.

## Detector

- `efficiency`: detector efficiency as a probability.
- `dark_count_rate_hz`: dark-count rate in hertz.
- `gate_width_s`: detection gate width in seconds.
- `readout_error_probability`: future readout-error probability.
- `double_click_policy`: `discard`, `random`, or `error`.

Future dark-count approximation:

```text
p_dark = 1 - exp(-dark_count_rate_hz * gate_width_s)
```

Phase 2 assumes every transmitted signal is detected and does not model dark
counts or double clicks.

## Post-Processing

- `qber_abort_threshold`: abort when QBER is greater than this value. Set to
  `None` to disable the abort threshold.
- `error_correction_efficiency`: `f_ec` in the simplified asymptotic BB84
  secret-fraction formula. Must be at least `1.0`.
- `sifting_enabled`: retained for validated configuration; Phase 2 BB84 always
  applies basis sifting.
- `privacy_amplification_enabled`: retained for future explicit privacy
  amplification steps.

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

If the abort threshold is enabled and exceeded, Phase 2 reports
`secret_key_rate_bps=0.0`.
