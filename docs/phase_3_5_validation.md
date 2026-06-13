# Phase 3.5 Validation Against Known QKD Trends

This note checks whether the current event-layer simulator follows known BB84
and fiber-QKD tendencies. It is not a security proof and it is not a
research-grade decoy-state key-rate validation. It is a sanity report for the
current Phase 3.5 model: single-photon BB84, fiber attenuation, detector
efficiency, dark counts, timing gates, jitter, dead time, and afterpulsing.

## References Used

- Bennett and Brassard's BB84 paper: [Quantum cryptography: Public key
  distribution and coin tossing](https://research.ibm.com/publications/quantum-cryptography-public-key-distribution-and-coin-tossing).
- Practical decoy-state context: Ma, Qi, Zhao, Lo, [Practical Decoy State for
  Quantum Key Distribution](https://arxiv.org/abs/quant-ph/0503005).
- Standard fiber-channel model and dark-count trends: [Optimizing the
  decoy-state BB84 QKD protocol parameters](https://link.springer.com/article/10.1007/s11128-021-03078-0).
- Realistic telecom fiber attenuation examples: Corning SMF-28 product pages
  and product-information sheets, e.g. [SMF-28 Ultra](https://www.corning.com/optical-communications/in/en/home/products/fiber/optical-fiber-products/smf-28-ultra.html)
  and ULL datasheets listed by Corning with around `0.16-0.18 dB/km` at
  `1550 nm`.
- Realistic detector scale examples: ID Quantique
  [ID230](https://www.idquantique.com/quantum-detection-systems/products/id230/),
  which lists up to `25%` detection probability, low dark count around `50 Hz`,
  timing resolution around `150 ps`, and adjustable dead time from `2 us` to
  `100 us`.

## Expected Trends

The current model should follow these coarse trends:

- Fiber attenuation should decay exponentially with distance:

```text
loss_db = alpha_db_km * distance_km + fixed_loss_db
eta_channel = 10 ** (-loss_db / 10)
```

- With random BB84 bases and no noise, approximately half of detections should
  survive sifting.
- Dark-count-only detections should produce random bits, so QBER should tend
  toward `0.5` as sample size grows.
- Dark counts should dominate QBER at long distances because signal detections
  fall with fiber loss while dark-click probability per gate stays fixed.
- Gaussian timing jitter should pass a centered rectangular gate with
  probability approximately:

```text
P(|jitter| <= gate_width_s / 2)
  = erf((gate_width_s / 2) / (sqrt(2) * jitter_std_s))
```

- Dead time should reduce detections when valid clicks arrive too close
  together.
- Afterpulsing should add false clicks after previous detections and raise QBER.

## Simulation Setup

All tables below were generated with the current code using a lightweight
deterministic backend for the BB84 measurement bit. The backend returns the
ideal BB84 measurement result for valid signal rounds, so the tables isolate
the event-layer effects.

Common parameters unless otherwise stated:

```text
pulses = 5_000
clock_rate_hz = 1_000_000
seed = 4242
source.emission_probability = 1.0
detector.efficiency = 1.0
detector.gate_width_s = 1e-6
detector.dark_count_rate_hz = 0
timing = ideal synchronization
```

The sample size is intentionally modest because this is a fast sanity report.
Small deviations from expected values are normal Monte Carlo variation,
especially where expected detection probability is below `1%`.

## Distance Sweep, `alpha = 0.2 dB/km`

This checks the core fiber-loss law. The trend matches the expected exponential
decay. At `50 km`, `10 dB` loss gives about `10%` gain. At `100 km`, `20 dB`
loss gives about `1%` gain.

| distance_km | expected_eta | sim_gain | detected | abs_error_pct_points | sifted_fraction | qber |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 100.000% | 100.000% | 5000 | 0.000 | 0.5016 | 0.0000 |
| 10 | 63.096% | 64.300% | 3215 | 1.204 | 0.4961 | 0.0000 |
| 25 | 31.623% | 33.300% | 1665 | 1.677 | 0.4883 | 0.0000 |
| 50 | 10.000% | 10.020% | 501 | 0.020 | 0.4790 | 0.0000 |
| 75 | 3.162% | 3.080% | 154 | 0.082 | 0.4740 | 0.0000 |
| 100 | 1.000% | 0.940% | 47 | 0.060 | 0.4043 | 0.0000 |
| 125 | 0.316% | 0.300% | 15 | 0.016 | 0.4667 | 0.0000 |
| 150 | 0.100% | 0.140% | 7 | 0.040 | 0.2857 | 0.0000 |

Interpretation:

- The gain follows `10^(-alpha L / 10)`.
- The sifted fraction is close to `0.5` when enough detections exist.
- At very low counts, the sifted fraction fluctuates more because only a few
  events are detected.

## Attenuation Variants

This checks that changing fiber loss coefficient changes the distance curve in
the expected direction. Lower `alpha` gives higher gain at the same distance.

| alpha_db_km | distance_km | expected_eta | sim_gain | detected |
|---:|---:|---:|---:|---:|
| 0.180 | 25 | 35.481% | 37.620% | 1881 |
| 0.180 | 50 | 12.589% | 13.040% | 652 |
| 0.180 | 100 | 1.585% | 1.520% | 76 |
| 0.200 | 25 | 31.623% | 33.300% | 1665 |
| 0.200 | 50 | 10.000% | 10.020% | 501 |
| 0.200 | 100 | 1.000% | 0.940% | 47 |
| 0.220 | 25 | 28.184% | 29.560% | 1478 |
| 0.220 | 50 | 7.943% | 7.980% | 399 |
| 0.220 | 100 | 0.631% | 0.520% | 26 |
| 0.275 | 25 | 20.535% | 21.220% | 1061 |
| 0.275 | 50 | 4.217% | 4.040% | 202 |
| 0.275 | 100 | 0.178% | 0.180% | 9 |
| 0.350 | 25 | 13.335% | 13.700% | 685 |
| 0.350 | 50 | 1.778% | 1.720% | 86 |
| 0.350 | 100 | 0.032% | 0.080% | 4 |

Interpretation:

- The monotonic ordering is correct: higher attenuation means fewer detections.
- At `100 km` and high attenuation, the expected count is only a few events, so
  relative Monte Carlo noise is large.

## Timing Jitter Sweep, `1 us` Gate

This checks the explicit timing layer. A photon is assigned to Bob's slot only
when it lands inside the gate. The simulated gain follows the rectangular-gate
Gaussian acceptance curve.

| jitter_std_ns | expected_acceptance | sim_gain | timing_discards | qber |
|---:|---:|---:|---:|---:|
| 0 | 100.000% | 100.000% | 0 | 0.0000 |
| 25 | 100.000% | 100.000% | 0 | 0.0000 |
| 50 | 100.000% | 100.000% | 0 | 0.0000 |
| 100 | 100.000% | 100.000% | 0 | 0.0000 |
| 200 | 98.758% | 98.660% | 67 | 0.0000 |
| 300 | 90.442% | 90.560% | 472 | 0.0000 |
| 500 | 68.269% | 67.600% | 1620 | 0.0000 |
| 700 | 52.495% | 51.860% | 2407 | 0.0000 |
| 1000 | 38.292% | 37.700% | 3115 | 0.0000 |
| 1500 | 26.112% | 25.800% | 3710 | 0.0000 |

Interpretation:

- Small jitter compared with gate width barely changes detection rate.
- Jitter comparable to or larger than the gate width produces timing discards.
- QBER stays zero because these are timing losses, not bit flips.

## Clock Offset Sweep, `1 us` Gate

This checks deterministic clock misalignment. With no jitter, a centered signal
is accepted while the offset magnitude is inside half the gate.

| offset_us | expected_acceptance | sim_gain | timing_discards | dominant_status |
|---:|---:|---:|---:|---:|
| -0.75 | 0.000% | 0.000% | 5000 | late |
| -0.50 | 100.000% | 100.000% | 0 | in_gate |
| -0.49 | 100.000% | 100.000% | 0 | in_gate |
| -0.25 | 100.000% | 100.000% | 0 | in_gate |
| +0.00 | 100.000% | 100.000% | 0 | in_gate |
| +0.25 | 100.000% | 100.000% | 0 | in_gate |
| +0.49 | 100.000% | 100.000% | 0 | in_gate |
| +0.50 | 100.000% | 100.000% | 0 | in_gate |
| +0.75 | 0.000% | 0.000% | 5000 | early |

Interpretation:

- The hard gate boundary behaves as expected.
- Negative offset makes the arriving signal late relative to Bob's shifted
  window; positive offset makes it early.

## Dark-Count-Only Sweep

This checks the detector's no-signal behavior. With no emitted photons, every
detection is a false detector click. The expected per-gate probability is:

```text
p_dark = 1 - exp(-dark_count_rate_hz * gate_width_s)
```

| dark_rate_hz | gate_width_ns | expected_p_dark | sim_gain | qber | detected |
|---:|---:|---:|---:|---:|---:|
| 100 | 1 | 0.000% | 0.000% | 0.0000 | 0 |
| 1000 | 1 | 0.000% | 0.000% | 0.0000 | 0 |
| 10000 | 1 | 0.001% | 0.000% | 0.0000 | 0 |
| 100000 | 1 | 0.010% | 0.000% | 0.0000 | 0 |
| 1000000 | 1 | 0.100% | 0.100% | 0.5000 | 5 |
| 10000 | 1000 | 0.995% | 1.260% | 0.5517 | 63 |
| 50000 | 1000 | 4.877% | 4.380% | 0.5000 | 219 |
| 100000 | 1000 | 9.516% | 9.420% | 0.4957 | 471 |

Interpretation:

- Dark-click gain follows `1 - exp(-rate * gate)`.
- QBER approaches `0.5` because dark bits are random.
- Very low probabilities need many more than `5_000` pulses to produce stable
  nonzero counts.

## Signal Plus Dark Counts Vs Distance

This is the most important qualitative QKD trend in the current model. Signal
detections decay with distance, but dark-click probability stays fixed per
window. Therefore QBER rises with distance and approaches the random-click
limit.

Parameters:

```text
alpha_db_km = 0.2
dark_count_rate_hz = 50_000
gate_width_s = 1e-6
double_click_policy = random
```

| distance_km | eta | p_dark | sim_gain | qber | detected | sifted |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 100.000% | 4.877% | 100.000% | 0.0231 | 5000 | 2508 |
| 25 | 31.623% | 4.877% | 36.460% | 0.0643 | 1823 | 902 |
| 50 | 10.000% | 4.877% | 14.380% | 0.1638 | 719 | 354 |
| 75 | 3.162% | 4.877% | 7.620% | 0.3005 | 381 | 193 |
| 100 | 1.000% | 4.877% | 5.520% | 0.4173 | 276 | 139 |
| 125 | 0.316% | 4.877% | 4.900% | 0.4531 | 245 | 128 |
| 150 | 0.100% | 4.877% | 4.740% | 0.4715 | 237 | 123 |

Interpretation:

- At short distance, signal dominates and QBER is low.
- At long distance, dark counts dominate and QBER approaches `0.5`.
- This is exactly the expected qualitative trend for a simple loss +
  dark-count BB84 model.

## Periodic Dead Time At `1 MHz`

This checks detector temporal memory. With one valid signal every microsecond
and detector efficiency `1.0`, dead time longer than one slot should suppress
periodic detections.

| dead_time_us | expected_period_slots | expected_gain | sim_gain | detected | dead_time_discards |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 1 | 100.000% | 100.000% | 5000 | 0 |
| 0.25 | 1 | 100.000% | 100.000% | 5000 | 0 |
| 0.50 | 1 | 100.000% | 100.000% | 5000 | 0 |
| 0.99 | 1 | 100.000% | 100.000% | 5000 | 0 |
| 1.00 | 1 | 100.000% | 100.000% | 5000 | 0 |
| 1.01 | 2 | 50.000% | 50.000% | 2500 | 2500 |
| 1.50 | 2 | 50.000% | 50.000% | 2500 | 2500 |
| 2.00 | 2 | 50.000% | 50.000% | 2500 | 2500 |
| 2.50 | 3 | 33.333% | 33.340% | 1667 | 3333 |
| 5.00 | 5 | 20.000% | 20.000% | 1000 | 4000 |

Interpretation:

- The trend is correct: increasing dead time reduces registered clicks.
- While generating this report, the exact-boundary cases `1.00 us` and
  `2.00 us` exposed a floating-point comparison edge. The detector now uses a
  tiny time-comparison tolerance and has a regression test ensuring that a
  click exactly at `available_at` is allowed.

## Afterpulse Sweep, `10%` Emission

This checks detector memory after previous detections. Afterpulsing should add
false clicks after prior clicks and increase QBER because those false bits are
random.

| afterpulse_probability | emission_probability | sim_gain | signal_baseline | afterpulse_clicks | qber |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 0.10 | 10.180% | ~10.000% | 0 | 0.0000 |
| 0.01 | 0.10 | 11.060% | ~10.000% | 44 | 0.0500 |
| 0.05 | 0.10 | 14.940% | ~10.000% | 238 | 0.1565 |
| 0.10 | 0.10 | 19.120% | ~10.000% | 447 | 0.2289 |
| 0.20 | 0.10 | 28.200% | ~10.000% | 901 | 0.3156 |
| 0.40 | 0.10 | 45.720% | ~10.000% | 1777 | 0.3584 |

Interpretation:

- More afterpulsing increases total detections above the signal baseline.
- QBER rises because afterpulse bits are independent of Alice's bit.
- This is qualitatively aligned with detector physics: afterpulsing is not a
  spontaneous dark count; it is conditional on a previous detection.

## ID230-Scale Detector Example

This is not a calibrated model of a specific commercial detector. It simply
uses parameters in the same order of magnitude as the ID230 product page:

```text
detector_efficiency = 0.25
dark_count_rate_hz = 50
dead_time_s = 2e-6
gate_width_s = 1e-9
alpha_db_km = 0.17
```

The `expected_signal_gain` column does not include dead-time suppression. The
simulation does, so the short-distance simulated gain is lower when detection
rate is high enough to hit the `2 us` dead time.

| profile | distance_km | alpha_db_km | detector_eff | dark_hz | dead_time_us | expected_signal_gain | sim_gain | detected | qber | dead_discards |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| teaching-default | 0 | 0.20 | 1.00 | 0 | 0.0 | 100.000% | 100.000% | 5000 | 0.0000 | 0 |
| teaching-default | 25 | 0.20 | 1.00 | 0 | 0.0 | 31.623% | 30.800% | 1540 | 0.0000 | 0 |
| teaching-default | 50 | 0.20 | 1.00 | 0 | 0.0 | 10.000% | 9.720% | 486 | 0.0000 | 0 |
| teaching-default | 75 | 0.20 | 1.00 | 0 | 0.0 | 3.162% | 3.160% | 158 | 0.0000 | 0 |
| teaching-default | 100 | 0.20 | 1.00 | 0 | 0.0 | 1.000% | 1.180% | 59 | 0.0000 | 0 |
| Corning-ULL-like | 0 | 0.17 | 0.25 | 50 | 2.0 | 25.000% | 20.320% | 1016 | 0.0000 | 1015 |
| Corning-ULL-like | 25 | 0.17 | 0.25 | 50 | 2.0 | 9.396% | 8.680% | 434 | 0.0000 | 434 |
| Corning-ULL-like | 50 | 0.17 | 0.25 | 50 | 2.0 | 3.531% | 3.840% | 192 | 0.0000 | 192 |
| Corning-ULL-like | 75 | 0.17 | 0.25 | 50 | 2.0 | 1.327% | 1.380% | 69 | 0.0000 | 69 |
| Corning-ULL-like | 100 | 0.17 | 0.25 | 50 | 2.0 | 0.499% | 0.560% | 28 | 0.0000 | 28 |

Interpretation:

- Detector efficiency scales the raw signal gain as expected.
- Dead time matters strongly near `0 km` when many photons arrive.
- At longer distances the lower arrival rate reduces dead-time pressure.

## What The Current Version Gets Right

- Fiber loss follows the expected dB exponential trend.
- BB84 basis sifting is near `1/2` when sample size is adequate.
- Dark-count-only detections are random and give QBER near `0.5`.
- Signal-plus-dark-count QBER rises with distance.
- Timing jitter follows the expected gate-acceptance curve.
- Clock offset behaves like a rectangular gate threshold.
- Dead time and afterpulsing produce the expected qualitative detector-memory
  behavior.
- Losses do not shift later slots; the simulator keeps one event per attempted
  time slot.

## What The Current Version Does Not Yet Validate

This report also clarifies the limits of the current implementation:

- This Phase 3.5 report validated the attenuation-only fiber model available
  at that point. Later phases add coherent misalignment, Aer phase/state noise,
  PMD, chromatic dispersion, Raman background, and polarization-dependent loss;
  those newer effects are covered by their own tests and documentation rather
  than by the curves in this historical report.
- This Phase 3.5 validation report uses the ideal single-photon source
  baseline. Phase 6 adds weak-coherent Poisson photon-number sampling and
  decoy-state statistics, but those newer diagnostics are not validated by the
  curves in this report.
- The secret-key-rate formula is still a simplified pedagogical estimate. It
  is not a finite-key decoy-state security analysis.
- Detector modeling is single-threshold and event-level. It is not yet a
  two-detector receiver with detector mismatch, basis-dependent efficiency, or
  detailed avalanche physics.
- The Monte Carlo examples use `5_000` pulses for speed. Production validation
  curves should use many more pulses and confidence intervals.

## Conclusion

The current version follows the known first-order trends for BB84 over lossy
fiber with event-level detector effects. The model is coherent for a TFG
teaching/research prototype: it gets the direction and scale right for loss,
dark counts, timing windows, dead time, and afterpulsing.

The next validation step should happen after Phase 3.6: compare the explicit
post-processing pipeline against known BB84/decoy-state key-rate curves and add
confidence intervals over multiple seeds.
