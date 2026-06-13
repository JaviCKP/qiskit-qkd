# Architecture

`qiskit-qkd` is Qiskit-first, not Qiskit-only. Qiskit owns the quantum circuit
path; the library owns the QKD event and post-processing path.

## Qiskit Layer

Use Qiskit for phenomena that are naturally represented as circuits or
primitives:

- `QuantumCircuit` objects for BB84 state preparation and measurement.
- `QuantumCircuit` objects for E91 Bell-pair preparation and angular
  measurements.
- Basis changes such as applying `H` before X-basis measurement.
- Statevector or primitive execution through current Qiskit result objects.
- Aer `NoiseModel` integration for quantum state noise and readout error.
- Controlled transpilation through Qiskit pass managers when requested.

Phase 3 uses this layer through `CircuitFactory.bb84_prepare_measure()` and
`QiskitSamplerBackend`. In the default noiseless path, the backend samples
Qiskit's exact final `Statevector` probabilities with its own seeded RNG; this
avoids one-shot primitive seed artifacts while preserving inspectable circuits.
When a caller provides a sampler, transpilation, or an Aer noise model, the
backend executes circuits in bounded primitive batches and extracts primitive
counts with `result[0].data.c.get_counts()`. Each protocol run keeps a fresh
JSON-safe execution summary on `SimulationResult.qiskit`.

Phase 4 extends this layer with `AerNoiseModelAdapter` and
`TranspilationOptions`. BB84 circuits include an explicit `id` instruction as a
channel marker between Alice's preparation and Bob's basis change. Aer
depolarizing and phase-damping errors attach to that marker; Aer readout error
attaches to measurement. Source preparation errors are sampled as logical BB84
preparation flips, while coherent channel misalignment appears as explicit
`ry`/`rz` gates. The backend records Qiskit/Aer versions, seeds, transpilation
options, primitive names, counts, and a compact noise summary.

BB84 now calls this backend only for pulses that were emitted by the source,
kept at least one surviving photon after channel loss, and were assigned to a
valid Bob timing gate. No circuit is executed for a source miss, a lost photon,
an out-of-window signal, or a pure dark-count/background event.

## QKD Event Layer

Keep QKD-specific classical and photonic behavior outside Qiskit:

- Emission events and photon-number metadata.
- Surviving photon counts after channel loss.
- Channel loss as transmission/no-click events.
- Polarization-dependent loss, temporal broadening, Raman crosstalk, and
  non-fiber optical link budgets.
- Detector efficiency, dark counts, and double clicks.
- Timing gates, jitter, clock offset/drift, dead time, and afterpulsing.
- Eve models and attack annotations.
- Sifting, QBER sampling, reconciliation diagnostics, privacy-amplification
  digests, abort decisions, and key-rate formulas.
- `Event`, `Metrics`, and `SimulationResult` serialization.

Phase 3 owns fiber attenuation and detector dark counts in this event layer.
Photon loss and dark counts are not Qiskit gates and are not represented with
`amplitude_damping`. Qiskit receives only the surviving, timing-valid signal
rounds whose BB84 state still needs quantum measurement.

Phase 4 preserves this boundary. Fiber attenuation, no-clicks, detector
efficiency, dark counts, optical background, dead time, afterpulsing, and
timing gates are excluded from the Aer `NoiseModel`; they remain event-layer
effects. Phase 6.1 keeps PMD, chromatic dispersion, polarization-dependent
loss, and Raman crosstalk on the same side of the boundary because they change
arrival times, link gain, or background-click rates rather than the one-qubit
unitary/noise circuit path.

## Analysis And Visualization Layer

Analysis helpers consume completed results and produce flat JSON-safe rows for
CSV, Pandas, plots, or notebooks. Phase 9 keeps visualization as an optional
consumer of those rows: `qiskit_qkd.visualization` imports Matplotlib only when
a plotting function is called, returns `Figure` objects, and never changes
scenario execution or security semantics.

## Phase 4: Aer Noise And Transpilation

Phase 4 adds the detectable quantum-state noise path without changing the
classical post-processing layer:

1. `QiskitSamplerBackend` reads source preparation-error probability and
   channel polarization rotations from the scenario.
2. `AerNoiseModelAdapter.from_scenario()` reads channel depolarizing and phase
   damping probabilities plus detector readout error.
3. The adapter creates a compact Aer `NoiseModel` for the BB84 channel marker
   and measurement.
4. The event-layer detector samples optical background independently from dark
   counts.
5. `TranspilationOptions` optionally applies Qiskit's pass-manager flow and
   records `optimization_level` and `seed_transpiler`.
6. `QiskitSamplerBackend` switches to Aer `SamplerV2` when a noise model is
   supplied and records the resulting provenance.

This phase deliberately does not implement Eve, decoy BB84, E91, dashboards,
CLI commands, or temporal channel characterization. Phase 4.1 adds the
characterization layer separately, above the static scenario model.

## Phase 4.1: Dynamic Communication Conditions

Phase 4.1 adds a time-parameter layer above the static `Scenario`:

1. `DynamicConfig` stores serializable `ParameterSchedule` objects on the
   scenario.
2. Each schedule binds a public `section.field` target, such as
   `source.preparation_error_probability` or
   `channel.background_count_rate_hz`, to a finite time profile.
3. `ParameterResolver` resolves an effective immutable scenario for a selected
   `time_s` by applying active schedules with `dataclasses.replace`.
4. `ChannelCharacterizer` converts effective scenarios into JSON-safe channel
   state rows.
5. `sweep_bb84_time()` runs BB84 at selected times and returns flat rows with
   metrics plus scheduled parameter values.

The protocol runner is still given ordinary scenarios. Dynamic schedules are a
configuration and analysis layer, not a hidden mutable clock inside BB84. This
keeps time studies reproducible and makes later plotting straightforward:
rows already contain `time_s`, effective parameter columns, and metrics.

Phase 4.1 deliberately does not add plotting dependencies, dashboards, per-pulse
nonstationary detector state changes inside one BB84 run, or security claims for
time-varying finite-key analysis.

## Phase 5: BB84 Eavesdropping

Phase 5 adds an explicit adversarial layer for BB84:

1. `EveConfig` stores the configured adversary on `Scenario`.
2. `eve_from_config()` builds either `NoEve` or `InterceptResendEve`.
3. BB84 invokes Eve only for emitted signal rounds with
   `surviving_photon_number > 0` and a valid timing-gate assignment.
4. If Eve intercepts, she measures in a random BB84 basis and resends her
   measured bit in that basis before Bob measures.
5. Event records store `eve_action`, `eve_basis`, `eve_detectable`, and
   structured Eve tags.
6. `Metrics` reports `eve_intercepted_fraction` and
   `eve_information_estimate`.

Eve is not accidental noise. Her actions are kept separate from dark counts,
background light, detector effects, and Aer noise. Hidden Eve diagnostics are
for simulator traceability; classical post-processing still uses only Alice and
Bob's public protocol data.

## Phase 6: Decoy-State BB84 Source Statistics

Phase 6 adds weak-coherent decoy-state infrastructure:

1. `DecoyIntensity` defines an intensity class with a mean photon number and
   selection probability.
2. `SourceConfig(kind="weak_coherent", decoy_intensities=...)` configures the
   source.
3. `WeakCoherentDecoySource` samples one intensity per attempted slot and then
   samples the photon number from a Poisson distribution.
4. The channel samples `surviving_photon_number` from
   `Binomial(n, eta_channel)` and keeps `transmitted` as a boolean summary.
5. The threshold detector applies efficiency to surviving photons with
   `1 - (1 - eta_detector)**K_survives`.
6. `Event.intensity_class`, `Event.photon_number`, and
   `Event.surviving_photon_number` trace the selected class, sampled photon
   number, and channel survivors.
7. `SimulationResult.decoy` reports per-intensity JSON-safe rows with pulses,
   photon-number categories, surviving photon totals, detections, sifted bits,
   QBER, and gain.

This phase is source/statistics infrastructure. It deliberately does not
implement finite-key estimators, photon-number-resolving detectors, or
composable security claims. Phase 6.2 adds the first asymptotic decoy estimator
and PNS Eve model on top of these traces.

## Phase 6.1: Fiber Impairments

Phase 6.1 adds first-order fiber impairments while preserving the layered
architecture:

1. `ChannelConfig` stores scalar parameters for PMD, chromatic dispersion,
   source spectral width, polarization-dependent loss, classical channel
   power, Raman coefficient, and Raman filter isolation.
2. `channels.impairments` owns the formulas. It computes temporal broadening,
   effective timing jitter, state-dependent PDL transmittance, Raman count
   rate, and effective background rate.
3. `prepare_physical_round()` receives Alice's bit and basis so PDL can affect
   photon survival before the Qiskit circuit path.
4. PMD and chromatic dispersion increase the timing-layer jitter used by
   `assign_timing()`, creating concrete `early`/`late` timing discards.
5. Raman crosstalk is added to the optical background rate passed to
   `ThresholdDetector`, producing `background` clicks without signal circuits.
6. `ChannelCharacterizer` exposes raw and derived impairment columns for
   plot-ready analysis rows.

This phase is intentionally not a full electromagnetic fiber solver. It does
not implement stochastic Jones-matrix propagation, spectral pulse-shape
evolution, wavelength-resolved Raman scattering, or dual-detector receiver
imbalance. The implemented models are deliberately compact, auditable, and
useful for parameter sweeps.

## Phase 6.2: Decoy Security And PNS

Phase 6.2 adds the first real decoy-security layer:

1. `estimate_vacuum_weak_decoy_security()` selects the highest positive
   intensity as signal, the next positive intensity as weak decoy, and the
   zero intensity as vacuum.
2. It computes the asymptotic vacuum+weak lower bound on single-photon yield
   `Y1`, the single-photon gain lower bound `Q1`, and the single-photon error
   upper bound `e1`.
3. `BB84Protocol` adds the estimate to `SimulationResult.decoy["security"]`
   whenever enough intensity rows exist and
   `PostProcessingConfig.decoy_security_estimation_enabled` is true.
4. `PhotonNumberSplittingEve` models an idealized QND photon-number attack:
   multi-photon pulses can be split without changing the BB84 state, while
   single-photon pulses can optionally be blocked to mimic channel loss.
5. PNS tags are stored on events, but PNS is not represented as accidental
   channel noise or an Aer `NoiseModel` component.
6. `analysis.decoy_rows_from_result()` converts the nested decoy summary into
   flat rows for CSV, Pandas, or plotting.

This is an asymptotic simulator diagnostic. It is useful for comparing normal,
attacked, and noisy weak-coherent BB84 scenarios, but it is not a finite-key or
composable security proof.

## Phase 7: E91 Bell-Pair QKD

Phase 7 adds the first entanglement-based protocol:

1. `E91Config` stores the Bell state, Alice/Bob measurement angles, setting
   pairs used for key, and signed CHSH terms.
2. `EntangledPairSource` samples whether a Bell pair is emitted in a clock
   slot.
3. `CircuitFactory.e91_bell_measure()` prepares the Bell pair, applies an
   optional source-pair Pauli error, marks Bob's channel with `id`, applies
   coherent Bob-channel rotations, and measures both qubits.
4. `E91Protocol` uses the existing event layer for Bob-arm loss, timing,
   detector efficiency, dark/background clicks, dead time, and afterpulses.
5. Alice and Bob use independent threshold-detector instances, even when they
   share the same `DetectorConfig`.
6. Coincident detections are grouped by public setting pair. Key pairs produce
   E91 QBER; CHSH pairs produce `Metrics.chsh_s`.
7. `SimulationResult.bell` and `analysis.bell_rows_from_result()` expose flat
   setting rows for plotting correlations and Bell violation.

E91 reuses the same Aer boundary as BB84. Depolarizing, phase damping, and
readout errors are attached through `AerNoiseModelAdapter`; loss, no-clicks,
detector efficiency, timing, dark counts, Bob-side background light, dead time,
and afterpulsing remain in the QKD event layer. Alice's local detector does not
receive Bob-arm Raman/background counts, and a Bob signal assigned to a
neighboring timing slot is not counted as an E91 coincidence for Alice's
original slot.

The first E91 implementation models one explicit quantum channel arm toward
Bob and keeps Alice local to the source. This is intentionally compact and
auditable. Dual-arm asymmetric links, SPDC multi-pair emission, loophole-free
Bell analysis, quantum PDL/loss channels for entangled states, and
device-independent finite-key security remain future work.

## Phase 8: Optical Channel Families

Phase 8 extends the event-layer channel family beyond fiber:

1. `ChannelConfig.kind` supports `space`, `free_space`, and `underwater` in
   addition to `ideal` and `fiber`.
2. `SpaceChannel` models diffraction-limited vacuum geometric loss using
   wavelength, transmitter aperture, receiver aperture, optional divergence,
   distance, and fixed optical loss.
3. `FreeSpaceChannel` adds atmospheric extinction plus optional per-pulse
   log-normal scintillation and Rayleigh pointing jitter.
4. `UnderwaterChannel` adds Beer-Lambert water extinction in inverse meters,
   optional fading, and scattering-induced temporal broadening.
5. `prepare_physical_round()` samples a pulse-level instantaneous
   transmittance when the channel provides `sample_transmittance(rng)`, then
   samples photon survival from that value.
6. `ChannelCharacterizer` exposes baseline loss, geometric transmittance,
   effective beam divergence, atmospheric loss, fading parameters, underwater
   extinction, and scattering broadening as flat rows for plotting.

These channels deliberately remain first-order link-budget models. They do not
implement orbital geometry, weather state, adaptive optics, full wave-optics
propagation, or wavelength-resolved underwater scattering. Quantum
depolarization and dephasing still use the explicit Aer boundary.

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

## Phase 3.6: Classical Reconciliation

Phase 3.6 adds an explicit classical post-processing layer after sifting:

1. Alice and Bob derive candidate sifted strings from the same detected
   same-basis slots.
2. A public, reproducible subset is revealed to estimate QBER.
3. If QBER is too high, the run aborts before trying to reconcile unrelated
   strings.
4. If QBER is acceptable, a pedagogical reconciliation protocol reveals parity
   or syndrome information and corrects Bob's candidate key.
5. The simulator accounts for the public leakage as `leak_ec`.
6. Optional privacy amplification reports a digest and output length for the
   corrected key material.

This phase is classical and should not call Qiskit. It should also distinguish
between what Alice and Bob can know through public messages and what the
simulator can inspect for validation. Hidden event fields such as
`detection_origin` may be useful for diagnostics, but the reconciliation
protocol must not depend on Bob knowing which individual clicks were dark
counts.

## Data Flow

1. `Scenario` stores validated parameters, optional dynamic schedules, and the
   central seed.
2. For temporal studies, `ParameterResolver` creates an effective immutable
   scenario at the requested `time_s`.
3. `BB84Protocol` samples Alice bits and bases, Bob bases, source emission,
   channel photon survival, and timing jitter from that seed.
4. If configured, Eve acts on surviving, timing-valid signal rounds before
   Bob's quantum measurement.
5. `CircuitFactory` builds one BB84 circuit per surviving timing-valid signal
   opportunity, using Eve's resent state when an attack occurred. Multi-photon
   pulses are represented in the event layer by `surviving_photon_number`; the
   circuit path still measures the BB84 state seen by Bob's threshold receiver.
6. `QiskitSamplerBackend` runs those circuits and returns Bob's measured signal
   bits. If configured, it applies Aer state/readout noise and controlled
   transpilation before primitive execution.
7. `ThresholdDetector` applies efficiency to the surviving photon count, then
   dark-count probability, effective optical background including Raman,
   double-click policy, dead time, and afterpulsing.
8. The protocol records an `Event` for each attempted pulse.
9. `sift_bb84_event()` marks detected matching-basis events as sifted.
10. `run_bb84_classical_postprocessing()` estimates QBER, reconciles the
   candidate strings pedagogically, and records leakage/final-key diagnostics.
11. `Metrics` aggregates counters, QBER, loss, gain, rates, abort status, and
    Eve diagnostics.
12. `SimulationResult` returns metrics, decoy statistics, classical
    diagnostics, provenance, Qiskit execution metadata, and the configured
    event sample.
13. Analysis helpers such as `ChannelCharacterizer` and `sweep_bb84_time()`
    collect JSON-safe rows for later plotting or comparison.

This boundary keeps the demo honest: Qiskit performs the quantum measurement,
while the QKD library performs photonic event sampling, detector bookkeeping,
and classical post-processing.
