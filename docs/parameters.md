# Parameters

Configuration fields include units in their names when units matter. Phase 3
uses the source, channel, and detector fields in BB84 execution through the
event layer. Phase 3.5 adds explicit timing fields in the same event layer.
Phase 3.6 adds explicit classical post-processing diagnostics. Phase 4 uses
selected source, channel, and detector noise fields to model preparation
imperfections, coherent channel misalignment, optical background, and Qiskit
Aer state/readout noise. Phase 4.1 adds dynamic schedules that resolve those
same static fields at selected times for characterization and temporal sweeps.
Phase 5 adds Eve parameters for BB84 intercept-resend studies. Phase 6 adds
weak-coherent decoy intensity classes and per-intensity result diagnostics.
Phase 6.1 adds first-order fiber impairment parameters for PMD, chromatic
dispersion, polarization-dependent loss, and Raman crosstalk. Phase 6.2 adds
asymptotic decoy diagnostics and photon-number-splitting Eve parameters. Phase 7
adds E91 Bell-pair settings and CHSH diagnostics. Phase 8 adds non-fiber
optical channel parameters for space, free-space/satellite, and underwater
links.

## Scenario

- `pulses`: number of attempted protocol rounds. Must be positive.
- `clock_rate_hz`: pulse clock rate in hertz. Used to convert counters into
  rates.
- `seed`: central deterministic seed for protocol sampling.
- `event_sample_size`: number of events to keep when `store_full_event_log` is
  false.
- `store_full_event_log`: when true, store every event in `SimulationResult`;
  when false, store a deterministic reservoir sample of up to
  `event_sample_size` events.
- `dynamic`: optional Phase 4.1 time-dependent parameter schedules. These are
  resolved into ordinary static scenarios before characterization or a temporal
  sweep.
- `eavesdropper`: optional Phase 5 adversarial model configuration.
- `e91`: optional Phase 7 E91 Bell-pair protocol configuration.

These are requested values. After execution,
`SimulationResult.provenance["effective_model"]` records which
source/channel/detector/protocol models were selected and which registered
parameter names were consumed or ignored.
Use it with the scenario digest, backend/Qiskit/Aer versions, primitive path,
and all recorded seeds when comparing or reproducing runs.

Derived duration:

```text
duration_s = pulses / clock_rate_hz
```

## E91

- `bell_state`: Bell state prepared by the E91 circuit. Supported values are
  `psi_minus` and `phi_plus`.
- `alice_angles_rad`: Alice measurement angles in radians.
- `bob_angles_rad`: Bob measurement angles in radians.
- `key_setting_pairs`: pairs of Alice/Bob setting indexes used for sifted key.
- `chsh_terms`: signed `(alice_setting, bob_setting, coefficient)` terms used
  to compute CHSH `S`. Exactly four unique pairs must form a complete 2x2
  setting grid; coefficients are integer `-1`/`+1` values whose sign product
  is `-1`. This is the family of equivalent CHSH witnesses with classical
  local bound `2`; empty, duplicate, incomplete, or bound-4 patterns are
  rejected.
- `bob_key_bit_flip`: when true, Bob flips key bits for the singlet
  anticorrelation key pair.
- `chsh_estimation_enabled`: when false, CHSH is not reported.
- `alice_detector`, `bob_detector`: optional independent detector overrides;
  when omitted, each arm receives a fresh detector built from the scenario
  detector configuration.
- `pair_emission_model`: `bernoulli` (legacy one-pair emission) or `poisson`
  (alias `multi_pair`) for effective Poisson pair counts.
- `pair_mean`: non-negative Poisson mean; if omitted, the source emission
  probability is used as the effective mean.

E91 assessment reports `observed_chsh_s`, `chsh_sample_size`,
`chsh_sample_size_by_term`, and a nullable `observed_threshold_exceeded`.
The Bell summary also records `classical_bound=2.0` explicitly.
`conclusion_scope="diagnostic_fair_sampling_no_significance_test"` means that
the detected-coincidence sample is post-selected: no significance test or
confidence interval is performed and no detection/locality loophole is closed.

For E91, `SourceConfig(kind="entangled_pair")` uses one Bell-pair
representative circuit per measurement opportunity. In `poisson` mode the
event layer samples an effective pair count and exposes multipair diagnostics;
the backend does not simulate an n-pair quantum state and this is not a
security proof. `source.preparation_error_probability` is interpreted as Bell
pair preparation imperfection: a sampled random Pauli error is applied to
Bob's qubit before channel propagation.

The first E91 implementation uses one explicit quantum channel arm toward Bob.
That arm reuses `ChannelConfig` loss, timing broadening, coherent rotations,
Aer state noise, Bob-side Raman/background rate, and the same detector model
used by BB84. Alice is local to the source but still measured through an
independent threshold detector instance. Alice does not receive Bob's
distance-dependent channel background in this model.

## Dynamic Schedules

Phase 4.1 models slowly changing communication conditions with finite time
profiles attached to `Scenario.dynamic`. A schedule has:

- `target`: a validated `section.field` path, for example
  `source.preparation_error_probability`,
  `channel.depolarizing_probability`, `channel.background_count_rate_hz`,
  `channel.polarization_dependent_loss_db`,
  `channel.classical_channel_power_mw`,
  `detector.efficiency`, `timing.clock_offset_s`, or
  `eavesdropper.intercept_probability`.
- `profile`: one of `ConstantProfile`, `LinearRampProfile`, or
  `ExponentialRampProfile`.

Supported target sections are `source`, `channel`, `detector`, `timing`, and
selected `post_processing` numeric fields. Targets are validated when the
schedule is built, so misspelled paths fail early instead of silently producing
bad analysis rows.

Profiles are active only in their window:

```text
active if start_s <= time_s <= end_s
inactive otherwise, so the base scenario value is used
```

The exponential profile uses an exponential easing curve:

```text
u = (time_s - start_s) / (end_s - start_s)
factor = (exp(curve * u) - 1) / (exp(curve) - 1)
value = start_value + (end_value - start_value) * factor
```

This can model an increasing optical background from zero or near-zero values,
unlike pure geometric interpolation.

Example:

```python
Scenario(
    ...,
    dynamic=DynamicConfig(
        parameter_schedules=(
            ParameterSchedule(
                target="source.preparation_error_probability",
                profile=ConstantProfile(start_s=0.0, end_s=3.0, value=0.08),
            ),
            ParameterSchedule(
                target="channel.background_count_rate_hz",
                profile=ExponentialRampProfile(
                    start_s=5.0,
                    end_s=8.0,
                    start_value=1_000.0,
                    end_value=200_000_000.0,
                ),
            ),
        ),
    ),
)
```

`ParameterResolver().scenario_at(scenario, time_s=6.5)` returns a new immutable
scenario with the active values applied and the consumed schedules removed, so
the result can be passed directly to a protocol runner. The original scenario
is not mutated. Protocol runners reject scenarios that still carry unresolved
dynamic schedules.

`sweep_bb84_time()` additionally requires BB84, at least two distinct
non-negative time points, and at least one supported schedule whose effective
value actually changes across those points. Missing schedules, constant
profiles, and ramps whose endpoints resolve to the same value are rejected;
they are not relabelled as temporal evolution.

For full link-state rows without running BB84, use
`ChannelCharacterizer().characterize_time(...)`. For protocol metrics at each
time point, use `analysis.sweep_bb84_time(...)`. Both return flat JSON-safe
rows so future plotting code can select columns directly.

Each requested time is resolved into an independent static run. The sweep does
not evolve one detector/channel state continuously and does not preserve dead
time, afterpulse, or fading memory between time points.
Sweep rows expose `requested_scenario_digest` and
`effective_scenario_digest`; compare the latter when checking the concrete
parameters executed at a point.

## Eavesdropper

- `kind`: `none`, `no_eve`, `intercept_resend`, `photon_number_splitting`,
  or `pns`. The aliases `no_eve` and `pns` normalize to `none` and
  `photon_number_splitting` so equivalent configurations serialize and digest
  identically.
- `intercept_probability`: probability that Eve intercepts a signal presented at
  the configured `attack_position`. This is meaningful for `intercept_resend`
  and must be in `[0, 1]`.
- `pns_split_probability`: probability that PNS Eve splits a multi-photon
  pulse. Meaningful for `kind="photon_number_splitting"` or `kind="pns"`.
- `pns_block_single_photon_probability`: probability that PNS Eve blocks a
  single-photon pulse to mimic loss.
- `attack_position`: discrete Eve placement, either `post_loss` (default) or
  `pre_loss`. `post_loss` samples channel survival and timing before Eve acts;
  `pre_loss` invokes Eve after source preparation and before channel survival.
  This is not a general composable two-segment channel model.

The intercept-resend model acts at the configured attack position. In the
default `post_loss` mode it acts only on emitted, transmitted, timing-valid
signal rounds:

```text
intercepted = rng.random() < intercept_probability
eve_basis = random choice from protocol.basis_choices
```

If `eve_basis == alice_basis`, Eve learns the physical prepared bit exactly and
resends the same BB84 state. If `eve_basis != alice_basis`, Eve obtains a random
bit and resends that bit in her basis. Under ideal BB84 conditions and
`intercept_probability = 1`, this produces the familiar approximate 25% QBER
on sifted bits.

For PNS, Eve uses photon-number diagnostics:

```text
photon_number >= 2:
  split with pns_split_probability
  forward the same BB84 state
  keep one photon and learn sifted bits after basis announcement

photon_number == 1:
  optionally block with pns_block_single_photon_probability
```

In `post_loss`, the PNS branch sees surviving photons; in `pre_loss`, it sees
the emitted photon number before channel survival. PNS does not add QBER by
itself. Its signature is intensity-dependent gain and extra Eve information on
multi-photon sifted events.

Eve diagnostics are written to event fields and tags. Aggregate metrics report:

```text
eve_intercepted_fraction = intercepted_signal_rounds / transmitted
eve_information_estimate = sifted_bits_known_by_eve / sifted
```

## Source

- `emission_probability`: probability that the source emits in a round.
- `mean_photon_number`: mean photon number for weak coherent or decoy-style
  sources. It may be `0.0` for vacuum decoy classes.
- `preparation_error_probability`: probability that the source preparation
  flips Alice's logical BB84 bit before basis encoding. The protocol samples
  this once into `PreparedState` before Eve or channel processing; the physical
  `prepared_bit` is then used by Eve and state-dependent channel effects, while
  `alice_bit` remains the logical value used for sifting.
- `decoy_intensities`: optional tuple of `DecoyIntensity` rows used by the
  weak-coherent family (`kind="weak_coherent"` or
  `kind="decoy_weak_coherent"`).

Phase 3 models only the ideal single-photon source case. Each emitted pulse has
`photon_number=1`; a non-emitted pulse has `photon_number=0` and can still
produce a detector click through dark counts or optical background.

In Phase 6, a weak-coherent source chooses one decoy intensity class per
attempted slot. Each `DecoyIntensity` has:

- `name`: unique label such as `signal`, `decoy`, or `vacuum`.
- `mean_photon_number`: Poisson mean `mu`.
- `selection_probability`: probability of choosing that intensity class.

The selection probabilities must sum to `1.0`. For weak-coherent decoy sources,
`emission_probability` is not the emission gate; emission is derived from the
sampled photon number:

```text
P(n | mu) = exp(-mu) * mu**n / n!
emitted = n > 0
```

If a weak-coherent kind is used without explicit `decoy_intensities`,
`mean_photon_number` is required and the source falls back to a single
`signal` class using that value.

Consequently, `emission_probability` requested together with a weak-coherent
source is retained for schema compatibility but does not control emission.
When explicit `decoy_intensities` are present, their per-class
`mean_photon_number` values take precedence over the top-level value. Inspect
the effective-model provenance instead of inferring behavior from an inactive
requested field.

## Channel

- `distance_km`: channel distance in kilometers.
- `attenuation_db_km`: fiber attenuation in dB per kilometer. Defaults to
  `0.2` (standard telecom fiber), matching the `FiberChannel` dataclass
  default; non-fiber channel kinds ignore it.
- `fixed_loss_db`: extra fixed optical loss in dB.
- `wavelength_nm`: optical wavelength used by diffraction-limited free-space
  and underwater geometric loss.
- `transmitter_aperture_m`: transmitter aperture diameter.
- `receiver_aperture_m`: receiver aperture diameter.
- `beam_divergence_rad`: optional beam divergence. When `0.0`, the channel
  derives `theta = 2.44 * wavelength_m / transmitter_aperture_m`.
- `atmospheric_extinction_db_km`: free-space atmospheric extinction in dB per
  kilometer.
- `scintillation_sigma`: dimensionless log-normal fading sigma for the
  `free_space` family (`free_space`, `atmospheric`, `satellite`) or underwater
  family (`underwater`, `water`, `marine`). `0.0` disables scintillation; the
  vacuum-space family (`space`, `deep_space`, `vacuum`) does not sample it.
- `pointing_jitter_rad`: RMS angular pointing jitter for the same free-space
  and underwater families. `0.0` disables pointing fading; the vacuum-space
  family does not sample it.
- `underwater_extinction_m_inv`: Beer-Lambert water extinction coefficient in
  inverse meters.
- `underwater_scattering_broadening_ns_per_m`: underwater scattering temporal
  broadening in ns per meter.
- `depolarizing_probability`: Qiskit/Aer state-noise parameter.
- `phase_damping_probability`: Qiskit/Aer state-noise parameter.
- `polarization_rotation_y_rad`: coherent channel rotation around the Bloch
  Y axis, inserted as an explicit Qiskit `ry` gate on surviving signal rounds.
- `polarization_rotation_z_rad`: coherent channel rotation around the Bloch
  Z axis, inserted as an explicit Qiskit `rz` gate on surviving signal rounds.
- `background_count_rate_hz`: optical background count rate in the receiver
  gate. Unlike `dark_count_rate_hz`, this is external channel/background light.
- `pmd_coefficient_ps_sqrt_km`: PMD coefficient in ps/sqrt(km).
- `chromatic_dispersion_ps_nm_km`: chromatic dispersion coefficient in
  ps/(nm km). It may be negative; the broadening uses its absolute value.
- `source_spectral_width_nm`: optical source spectral width used by the
  first-order chromatic-dispersion model. It is physically a source property,
  but remains under `ChannelConfig` for wire-format/digest compatibility;
  moving it to `SourceConfig` is a future migration.
- `polarization_dependent_loss_db`: PDL difference in dB between the preferred
  and suppressed eigenstates.
- `pdl_axis_basis`: BB84 basis (`Z` or `X`) defining the preferred PDL axis.
- `pdl_axis_bit`: bit (`0` or `1`) defining the preferred state on that axis.
  PDL evaluates the physical `PreparedState.prepared_bit`, so a source
  preparation error can change which PDL branch is sampled; it does not use
  Alice's logical `alice_bit`.
- `classical_channel_power_mw`: co-propagating classical-channel power in mW.
- `raman_coefficient_hz_mw_km`: Raman count-rate coefficient in Hz/(mW km).
- `raman_filter_isolation_db`: optical filter isolation applied to Raman noise.

Fiber physical-loss formula:

```text
loss_db = attenuation_db_km * distance_km + fixed_loss_db
eta_channel = 10 ** (-loss_db / 10)
```

For each emitted photon:

```text
transmitted = rng.random() < eta_channel
```

Non-fiber channel kinds:

- `space` (aliases `deep_space`, `vacuum`): vacuum/deep-space optical link with
  diffraction-limited geometric loss and fixed optical loss.
- `free_space` (aliases `atmospheric`, `satellite`): atmospheric or satellite
  link with geometric loss, atmospheric extinction, optional scintillation,
  and optional pointing jitter.
- `underwater` (aliases `water`, `marine`): water link with geometric loss,
  Beer-Lambert extinction, optional turbulence/pointing fading, and optional
  scattering broadening.

Geometric aperture coupling:

```text
theta =
  beam_divergence_rad                         if configured above zero
  2.44 * wavelength_m / transmitter_aperture_m otherwise

D_beam(L) = transmitter_aperture_m + theta * distance_m
eta_geom = min(1, (receiver_aperture_m / D_beam(L))**2)
```

Free-space baseline:

```text
eta_base =
  eta_geom
  * 10 ** (-(fixed_loss_db + atmospheric_extinction_db_km * distance_km) / 10)
```

Underwater baseline:

```text
eta_base =
  eta_geom
  * exp(-underwater_extinction_m_inv * distance_m)
  * 10 ** (-fixed_loss_db / 10)
```

For every non-fiber optical family, `transmittance()` returns the stable
baseline used by `ChannelCharacterizer`. During event simulation only
the fading-capable free-space and underwater families apply the following
scintillation/pointing sample; the vacuum-space family uses its stable baseline:

```text
f_scint ~ LogNormal(-scintillation_sigma**2 / 2, scintillation_sigma)
r_point ~ Rayleigh(pointing_jitter_rad * distance_m)
f_point = exp(-2 * (r_point / beam_radius_m)**2)
eta_instant = clip01(eta_base * f_scint * f_point)
```

All photons in the same emitted pulse use the same sampled `eta_instant`; this
models a pulse-level channel state before binomial photon survival is sampled.

For a weak-coherent pulse with `n > 1`, the channel event samples the number of
photons that survive the fiber:

```text
K_survives ~ Binomial(n, eta_channel)
transmitted = K_survives > 0
```

With PDL enabled, the per-photon survival probability is state dependent:

```text
pdl_min_factor = 10 ** (-polarization_dependent_loss_db / 10)
pdl_factor =
  1.0                              for the configured axis bit
  pdl_min_factor                   for the orthogonal axis bit
  (1.0 + pdl_min_factor) / 2       for the conjugate BB84 basis
eta_state = eta_channel * pdl_factor
K_survives ~ Binomial(n, eta_state)
```

The factor never exceeds `1.0`, so PDL is modeled as extra loss rather than a
gain boost.

Photon loss is represented as an event-level no-click opportunity. It is not
modeled with Qiskit `amplitude_damping`, because fiber loss removes the photon
from the detected event stream rather than relaxing a computational qubit from
`|1>` to `|0>`.

In Phase 4, `depolarizing_probability` and `phase_damping_probability` are
translated by `AerNoiseModelAdapter` into Aer errors on the explicit BB84
channel marker operation (`id`). They affect only signal rounds that survived
the event-layer source/channel/timing path.

Coherent polarization rotations are not hidden inside `NoiseModel`; they are
visible gates in the BB84 circuit after the channel marker and before Bob's
basis change. Optical background remains event-layer noise:

```text
p_background = 1 - exp(-background_count_rate_hz * gate_width_s)
```

Phase 6.1 adds Raman crosstalk from co-propagating classical channels:

```text
raman_count_rate_hz =
  raman_coefficient_hz_mw_km
  * classical_channel_power_mw
  * distance_km
  * 10 ** (-raman_filter_isolation_db / 10)

effective_background_count_rate_hz =
  background_count_rate_hz + raman_count_rate_hz
```

`ThresholdDetector` receives the effective background rate. Raman-created
clicks are recorded as `detection_origin="background"` because Bob's receiver
does not distinguish them from other optical background counts.

PMD and chromatic dispersion are timing impairments:

```text
pmd_broadening_s =
  pmd_coefficient_ps_sqrt_km * sqrt(distance_km) * 1e-12

chromatic_broadening_s =
  abs(chromatic_dispersion_ps_nm_km)
  * distance_km
  * source_spectral_width_nm
  * 1e-12

temporal_broadening_s =
  sqrt(
    pmd_broadening_s**2
    + chromatic_broadening_s**2
    + scattering_broadening_s**2
  )

scattering_broadening_s =
  underwater_scattering_broadening_ns_per_m
  * distance_m
  * 1e-9

effective_jitter_std_s =
  sqrt(jitter_std_s**2 + temporal_broadening_s**2)
```

`ChannelCharacterizer` reports all raw impairment parameters plus the derived
columns above, `pdl_min_transmittance`, `raman_count_rate_hz`, and
`effective_background_count_rate_hz`. It also reports non-fiber channel columns
such as `channel_kind`, `geometric_transmittance`,
`effective_beam_divergence_rad`, `atmospheric_loss_db`,
`scintillation_sigma`, `pointing_jitter_rad`, and underwater extinction or
scattering parameters.

## Decoy-State Statistics

`SimulationResult.decoy` is populated when events carry an `intensity_class`.
Rows are keyed by intensity name and expose flat JSON-safe counters:

```text
pulses              selected slots for that intensity
selection_fraction  pulses / scenario.pulses
emitted             photon_number > 0
zero_photon         photon_number == 0
single_photon       photon_number == 1
multi_photon        photon_number > 1
surviving_photons   sum of photons that survived channel loss
transmitted         at least one photon survived the channel
detected            Bob recorded a detection after detector effects
sifted              detected same-basis BB84 events
errors              sifted Alice/Bob bit mismatches
gain                detected / pulses
qber                errors / sifted, or legacy 0.0 when sifted == 0
```

These statistics make the decoy effects visible and easy to plot. Phase 6.2
also adds `decoy["security"]` with asymptotic vacuum+weak estimates:

```text
Y1_L  lower bound on single-photon yield
Q1_L  lower bound on single-photon gain = mu * exp(-mu) * Y1_L
e1_U  upper bound on single-photon error rate
R     asymptotic decoy secret-rate diagnostic
```

For signal intensity `mu`, weak decoy `nu`, and vacuum yield `Y0`:

```text
Y1_L =
  mu / (mu * nu - nu**2)
  * (Q_nu exp(nu) - Q_mu exp(mu) nu**2 / mu**2
     - (mu**2 - nu**2) Y0 / mu**2)

e1_U = (E_nu Q_nu exp(nu) - 0.5 Y0) / (nu Y1_L)
```

The estimator is asymptotic and clips finite-sample Monte Carlo artifacts to
valid probability ranges. For BB84 diagnostic rates, error rates greater
than or equal to `0.5` contribute no privacy term, so the reported secret-rate
diagnostic cannot become positive again because `h2(1) == 0`. It is not a
finite-key or composable proof.

## Detector

Both `DetectorConfig.kind="ideal"` and `kind="threshold"` currently construct
the same effective `ThresholdDetector`. The `ideal` label does not override
explicit efficiency/noise/memory fields; an actually idealized detector needs
efficiency `1.0` and zero dark counts, dead time, afterpulsing, and readout
error. The effective-model provenance records the concrete class.

- `efficiency`: detector efficiency as a probability.
- `dark_count_rate_hz`: dark-count rate in hertz.
- `gate_width_s`: detection gate width in seconds.
- `readout_error_probability`: Aer readout-error probability when using
  `AerNoiseModelAdapter`.
- `double_click_policy`: `discard`, `random`, or `error`.
- `dead_time_s`: time after a detection during which the detector is
  unavailable.
- `afterpulse_probability`: per-gate probability of a false click after a
  previous detection.
- `afterpulse_tau_s`: optional positive decay constant. With a previous firing
  at `t_prev`, the current probability is
  `p_ap = afterpulse_probability * exp(-max(0, t - t_prev) / afterpulse_tau_s)`.
  `None` preserves the legacy constant per-gate probability.

Dark-count approximation:

```text
p_dark = 1 - exp(-dark_count_rate_hz * gate_width_s)
```

Phase 3.5 detector behavior:

- If no signal arrives and no dark count occurs, the event is not detected.
- If no signal arrives and a dark count occurs, Bob receives a random bit with
  `detection_origin="dark"`.
- If no signal arrives and an optical background click occurs, Bob receives a
  random bit with `detection_origin="background"`.
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

Detector efficiency is sampled before dark-count resolution. For one surviving
photon this is the ordinary Bernoulli model:

```text
signal_click = signal_present and rng.random() < efficiency
```

For a multi-photon pulse with `K_survives` photons after channel loss, the
threshold detector samples whether at least one of them is detected:

```text
p_signal_click = 1 - (1 - efficiency)**K_survives
signal_click = signal_present and rng.random() < p_signal_click
```

Together with channel sampling this gives the correct marginal signal-click
probability for an `n`-photon pulse:

```text
P(signal click | n) = 1 - (1 - eta_channel * efficiency)**n
```

The event-layer detector does not apply `readout_error_probability` directly.
In Phase 4, `AerNoiseModelAdapter` translates it into an Aer `ReadoutError`
attached to measurement. Detector efficiency, dark counts, dead time, and
afterpulsing remain event-layer effects.

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
  Bob slot only when the arrival is inside that slot's detection gate.

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
timing_status = no_signal | in_gate | early | late | assigned_nearest | ambiguous | dead_time
```

Lost photons should still produce no signal click. A dark count should still be
attached to the Bob gate in which it occurs. Timing fields decide whether a
signal can legitimately be measured in a gate; they do not shift later slots to
fill a loss.

With `slot_assignment_policy="nearest"`, a signal that lands in another Bob
gate is measured with that gate's Bob basis, but public BB84 sifting still
discards it because `assigned_slot != time_slot`. Such shifted signal arrivals
are counted in `metrics.timing_discards`, just like early or late transmitted
signals that cannot be assigned to any gate.

When Phase 6.1 PMD or chromatic-dispersion parameters are non-zero, the timing
layer uses `effective_jitter_std_s` instead of the bare `jitter_std_s`. The
stored `TimingConfig` is not mutated; the effective value is derived during
physical-round preparation and exposed by `ChannelCharacterizer`.

## Post-Processing

- `qber_abort_threshold`: abort when QBER is greater than this value. Set to
  `None` to disable the abort threshold.
- `qber_sample_fraction`: fraction of sifted bits revealed publicly for QBER
  estimation.
- `error_correction_efficiency`: `f_ec` in the simplified asymptotic BB84
  secret-fraction formula. Must be at least `1.0`.
- `reconciliation_block_size`: block size for the pedagogical block-parity
  reconciliation pass.
- `sifting_enabled`: when true (default), BB84 keeps only detections where
  Alice and Bob used the same basis. When false, every valid detection becomes
  a key candidate, so mismatched-basis rounds contribute random bits and ideal
  two-basis BB84 trends toward 25% QBER.
- `privacy_amplification_enabled`: when true, report a reproducible digest and
  final length for the corrected key material.
- `decoy_security_estimation_enabled`: when true, BB84 decoy runs add a
  `SimulationResult.decoy["security"]` diagnostic row whenever the required
  signal, weak decoy, and vacuum rows are present.
- `decoy_security_method`: validated decoy estimator selector. Use
  `"vacuum_weak_asymptotic"` for the current asymptotic diagnostic, or `"none"` to
  keep only observed per-intensity statistics.

The Phase 3.6 flow is:

```text
sifted_alice_bits, sifted_bob_bits
  -> reveal reproducible QBER sample
  -> abort if estimated_qber > qber_abort_threshold
  -> reconcile remaining bits
  -> account leak_ec
  -> verify residual_mismatches == 0 (else no final key)
  -> privacy_amplify(corrected_key, final_key_length)
```

`verification_passed` reports whether the reconciled strings match exactly.
When residual mismatches remain, Alice and Bob hold different strings, so the
result reports `final_key_length=0` and no digest, mirroring the error
verification exchange of real systems.

With `qber_sample_fraction=0`, `qber_sample_size` is zero: no bits are publicly
revealed. For pedagogical validation the implementation nevertheless computes
the decision value from the complete sifted strings. Assessment labels this
oracle-like value `qber_method="full_sifted_key_diagnostic"`; it must not be
interpreted as an estimate available to Alice and Bob through the modeled
public transcript.

Error correction is meaningful only when Alice and Bob's sifted strings are
already correlated. If dark counts dominate and QBER approaches `0.5`, the run
should abort instead of attempting to force a shared key from random strings.
The block-parity reconciliation is pedagogical. It is not Cascade, LDPC,
finite-key analysis, or a composable security proof.

QBER:

```text
qber = errors / sifted        if sifted > 0
qber = 0                      if sifted == 0  # legacy numeric placeholder
```

The authoritative interpretation of the second branch is
`assessment.qber_defined=False`, `qber_value=None`, and
`data_status="insufficient_data"`, not "zero observed errors".

Pedagogical BB84 secret fraction:

```text
h2(q) = -q log2(q) - (1 - q) log2(1 - q)
secret_fraction = 0                                         if qber >= 0.5
secret_fraction = max(0, 1 - f_ec * h2(qber) - h2(qber))    otherwise
```

When privacy amplification is enabled, `estimated_qber >= 0.5` also reports no
final key material even if `qber_abort_threshold=None` disables the early abort
gate.

Rates:

```text
gain = detected / pulses
raw_detection_rate_hz = gain * clock_rate_hz
sifted_key_rate_bps = (sifted / pulses) * clock_rate_hz
secret_key_rate_bps = sifted_key_rate_bps * secret_fraction
```

If the abort threshold is enabled and exceeded, Phase 3 reports
`secret_key_rate_bps=0.0`.

The following outputs answer different questions and must not be collapsed
into a single "secure" boolean:

- `metrics.abort`: legacy flag comparing aggregate `metrics.qber`
  (`errors/sifted`) with the configured threshold; the legacy rate formula
  also uses that aggregate QBER.
- `assessment.threshold_exceeded` and `threshold_decision_source`: the
  interpreted classical/legacy/disabled threshold decision. With a revealed
  sample this can legitimately differ from the aggregate legacy flag.
- `assessment.verification_status`: whether reconciliation was verified.
- `assessment.key_status`: whether this educational pipeline estimated key
  material and, if not, why.
- `assessment.rate_estimate_status`: whether the pedagogical asymptotic rate is
  available and whether it conflicts with the key status.
- `assessment.security_scope`, `finite_key`, and `composable`: the scientific
  scope; currently `pedagogical_asymptotic_diagnostic`, `False`, and `False`.

Thus a positive `secret_key_rate_bps` is not a finite-key bound, composable
proof, verified production key, or guarantee for a real implementation.

For repeated sweeps, `summarize_metric_rows` adds Wilson score intervals for
pooled proportions (QBER, gain, and binary decisions) and two-sided Student-t
intervals for means across independent repeats. An undefined interval is
serialized as `bounds=[null, null]` when its denominator is zero or fewer than
two repeats are available. Descriptive `p05`/`p95` columns are empirical
percentiles, not confidence bounds and not composable-security failure
probabilities.

In Phase 3, `loss_db` is the active channel loss for the scenario. `gain`
continues to mean detections per attempted pulse, including dark-count
detections.
