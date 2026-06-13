# Domain Model

The domain model defines the smallest useful data objects for QKD simulations.
The model uses dataclasses with explicit validation and JSON serialization.
Phase 3 adds BB84 execution with fiber channel loss, detector efficiency, dark
counts, and double-click handling on top of these objects. Phase 3.5 adds
explicit timing synchronization, detector dead time, and afterpulsing.
Phase 3.6 adds explicit pedagogical reconciliation and optional privacy
amplification diagnostics. Phase 4 adds Aer state/readout noise and
transpilation metadata. Phase 4.1 adds dynamic parameter schedules and
channel characterization rows for time-dependent communication studies. Phase
5 adds BB84 Eve configuration and trace diagnostics. Phase 6 adds
weak-coherent decoy-state source classes and per-intensity statistics. Phase
6.1 adds fiber-impairment fields and characterization columns for PMD,
chromatic dispersion, PDL, and Raman crosstalk. Phase 6.2 adds asymptotic
decoy-security diagnostics and PNS Eve traces. Phase 7 adds E91 Bell-pair
configuration, CHSH diagnostics, and plot-ready Bell rows. Phase 8 adds
non-fiber optical channel configuration for space, free-space/satellite, and
underwater links. Phase 9 adds optional derived metric rows and Matplotlib
figures on top of these analysis outputs. Dashboards and CLI commands remain
future work.

## Scenario

`Scenario` is the complete reproducible setup for one simulation run. It stores:

- `pulses`: number of attempted emissions.
- `clock_rate_hz`: source clock rate.
- `seed`: central seed used to create deterministic random generators.
- `protocol`, `source`, `channel`, `detector`, `timing`, `post_processing`,
  and E91 configs.
- `eavesdropper`: optional Eve model configuration.
- `dynamic`: optional schedules that resolve time-dependent parameter values
  into ordinary static scenarios for characterization or temporal sweeps.
- `event_sample_size`: maximum sampled event records to keep.
- `store_full_event_log`: disabled by default to avoid storing millions of rows.
- `metadata`: JSON-safe extra labels.

The same scenario and seed produce the same digest and reproducibility summary.

## Config Objects

The initial config objects are intentionally small:

- `ProtocolConfig`: protocol name and basis choices.
- `SourceConfig`: source kind, emission probability, mean photon number,
  preparation error probability, and optional decoy intensity classes.
- `DecoyIntensity`: weak-coherent intensity class with a name, mean photon
  number, and selection probability.
- `ChannelConfig`: channel kind, `distance_km`, `attenuation_db_km`,
  `fixed_loss_db`, free-space aperture/link-budget parameters, underwater
  extinction/scattering parameters, depolarizing probability, phase damping
  probability, coherent polarization rotations, optical background rate,
  PMD/CD parameters, PDL parameters, and Raman crosstalk parameters.
- `DetectorConfig`: detector kind, efficiency, `dark_count_rate_hz`,
  `gate_width_s`, `dead_time_s`, `afterpulse_probability`, readout error
  probability, and double-click policy.
- `TimingConfig`: propagation delay, jitter, Bob clock offset/drift, and slot
  assignment policy.
- `PostProcessingConfig`: sifting flag, QBER abort threshold, error correction
  efficiency, QBER sample fraction, reconciliation block size, privacy
  amplification flag, and decoy security estimator controls.
- `EveConfig`: adversarial model kind, intercept probability, and PNS split
  or single-photon blocking probabilities.
- `E91Config`: Bell state, Alice/Bob angular settings, key setting pairs, CHSH
  terms, Bob key-bit flip, and CHSH estimation switch.
- `DynamicConfig` and `ParameterSchedule`: optional Phase 4.1 schedules that
  bind validated `section.field` targets to finite time profiles.

Values are checked at construction time. Probabilities must be in `[0, 1]`,
rates and distances must be non-negative, and time windows must be positive.

`ChannelConfig` fiber impairment fields are scalar and JSON-safe:

- `pmd_coefficient_ps_sqrt_km`, `chromatic_dispersion_ps_nm_km`, and
  `source_spectral_width_nm` derive timing broadening.
- `polarization_dependent_loss_db`, `pdl_axis_basis`, and `pdl_axis_bit`
  derive state-dependent survival probability.
- `classical_channel_power_mw`, `raman_coefficient_hz_mw_km`, and
  `raman_filter_isolation_db` derive Raman background count rate.

`ChannelConfig` non-fiber optical fields are also scalar and JSON-safe:

- `wavelength_nm`, `transmitter_aperture_m`, `receiver_aperture_m`, and
  `beam_divergence_rad` derive geometric aperture coupling for `space`,
  `free_space`, and `underwater` channels.
- `atmospheric_extinction_db_km`, `scintillation_sigma`, and
  `pointing_jitter_rad` configure free-space/satellite extinction and fading.
- `underwater_extinction_m_inv` and
  `underwater_scattering_broadening_ns_per_m` configure Beer-Lambert water loss
  and scattering timing broadening.

## Dynamic Parameters

Dynamic parameters are intentionally a configuration and analysis layer. A
`Scenario` can carry schedules such as:

```python
ParameterSchedule(
    target="channel.background_count_rate_hz",
    profile=ExponentialRampProfile(
        start_s=5.0,
        end_s=8.0,
        start_value=1_000.0,
        end_value=200_000_000.0,
    ),
)
```

`ParameterResolver().scenario_at(scenario, time_s=6.5)` returns a new immutable
scenario with active schedules applied and consumed. `ChannelCharacterizer`
and `analysis.sweep_bb84_time()` use the same mechanism to produce flat rows
with `time_s`, effective parameter columns, and metrics. `BB84Protocol.run()`
receives an ordinary static scenario, does not mutate parameters internally
during a single run, and rejects scenarios with unresolved dynamic schedules.

Decoy summaries follow the same analysis-friendly style:
`analysis.decoy_rows_from_result()` converts `SimulationResult.decoy` into flat
rows with `row_type="intensity"` or `row_type="security"` for direct plotting
or CSV export.

E91 Bell summaries follow the same pattern:
`analysis.bell_rows_from_result()` converts `SimulationResult.bell` setting
rows into flat JSON-safe data for plotting CHSH correlations.

Non-fiber channel characterization follows the same plot-ready style:
`ChannelCharacterizer` includes `channel_kind`, `geometric_transmittance`,
`effective_beam_divergence_rad`, `atmospheric_loss_db`,
`scintillation_sigma`, `pointing_jitter_rad`, `underwater_extinction_m_inv`,
and `scattering_broadening_s` in its flat rows.

Phase 9 visual analytics follows the same boundary:
`analysis.metric_rows_from_results()` and `analysis.add_derived_metrics()`
produce enriched rows, while `qiskit_qkd.visualization` consumes rows and
returns Matplotlib figures only when the optional `plot` extra is installed.

## Eve Diagnostics

Eve is configured separately from source, channel, detector, and Aer noise. The
default `EveConfig(kind="none")` leaves BB84 unchanged. With
`kind="intercept_resend"`, Eve can intercept each surviving signal with a
configured probability, measure in a random BB84 basis, and resend her measured
state to Bob.

Event records use the existing Eve fields for traceability:

- `eve_action`: the adversarial action, currently `intercept_resend`.
- `eve_basis`: Eve's measurement/resend basis.
- `eve_detectable`: true when Eve used a basis different from Alice's basis.
- `tags`: simulator diagnostics such as Eve's measured bit and resent state.

`Metrics.eve_intercepted_fraction` reports the fraction of transmitted signal
rounds intercepted, and `Metrics.eve_information_estimate` reports the fraction
of sifted bits for which Eve used Alice's basis. These are hidden simulator
diagnostics and are not inputs to sifting or reconciliation.

## Decoy Diagnostics

Decoy-state BB84 is configured at the source layer. With
`SourceConfig(kind="weak_coherent", decoy_intensities=...)`, each attempted slot
selects one `DecoyIntensity` and samples a Poisson photon number. The channel
then samples `surviving_photon_number`, while `transmitted` remains the boolean
summary `surviving_photon_number > 0`. Event records store the selected
`intensity_class`, sampled `photon_number`, and surviving photon count; those
fields flow through timing, detection, sifting, Eve traces, and result
serialization without changing the classical BB84 API.

`SimulationResult.decoy` stores aggregate rows keyed by intensity class. Each
row reports the selected pulse count, photon-number categories, transmitted and
detected counts, total surviving photons, sifted bits, errors, gain, QBER, and
the configured intensity metadata when available. These are simulator
diagnostics for characterization. `SimulationResult.decoy["security"]` stores
the Phase 6.2 asymptotic vacuum+weak estimator when signal, weak decoy, and
vacuum rows are present. It reports `Y1`, `Q1`, `e1`, warnings, and a decoy
secret-rate diagnostic; it is not a finite-key security bound.

## Fiber Impairment Diagnostics

Fiber impairments are configured on `ChannelConfig` but derived in
`channels.impairments` and reported through `ChannelCharacterizer`. This keeps
the data model compact while making plots and audits easy.

`ChannelState.to_dict()` includes both raw parameters and derived values:

- `pmd_broadening_s`, `chromatic_broadening_s`,
  `temporal_broadening_s`, and `effective_jitter_std_s`.
- `pdl_min_transmittance`, `pdl_axis_basis`, and `pdl_axis_bit`.
- `raman_count_rate_hz` and `effective_background_count_rate_hz`.

Events still store the ordinary physical lifecycle fields. PDL is visible
through changed `transmitted`/`surviving_photon_number` statistics, PMD/CD
through `timing_status` and `timing_discards`, and Raman through background
detections.

## Results

`Event` represents one sampled protocol round. It contains trace fields for
Alice and Bob bases, emission, timing, sampled photon number, surviving photon
number, transmission, detection, sifting, errors, decoy intensity, Eve
action/basis markers, and optional tags.

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

`SimulationResult.classical` stores post-processing diagnostics such as QBER
sample size, revealed sample count, `leak_ec`, corrected-key length, residual
mismatch count, privacy-amplified length, and final-key digest for reproducible
small examples.

`SimulationResult` stores the scenario, metrics, classical diagnostics, decoy
diagnostics, provenance, Qiskit execution summary, library version, and an
optional event sample. Provenance includes the seed, scenario digest, library
version, and RNG family. The Qiskit summary is JSON-safe and stores counts,
circuit metadata samples, primitive name, execution sizing, Qiskit/Aer
versions, seeds, transpilation settings, and compact `NoiseModel` diagnostics
rather than raw `QuantumCircuit` objects.

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
