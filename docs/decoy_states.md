# Decoy-State BB84

Phase 6 adds weak-coherent decoy-state infrastructure for BB84. Phase 6.2 adds
the first real asymptotic decoy-security estimator and a photon-number-splitting
Eve model. The result is still not a finite-key or composable security proof,
but it now estimates the single-photon terms that decoy BB84 needs.

## Core API

Configure a weak-coherent source with intensity classes:

```python
from qiskit_qkd import DecoyIntensity, Scenario, SourceConfig

scenario = Scenario(
    pulses=4_096,
    clock_rate_hz=1_000_000.0,
    seed=61,
    source=SourceConfig(
        kind="weak_coherent",
        decoy_intensities=(
            DecoyIntensity(
                "signal",
                mean_photon_number=0.6,
                selection_probability=0.7,
            ),
            DecoyIntensity(
                "decoy",
                mean_photon_number=0.2,
                selection_probability=0.2,
            ),
            DecoyIntensity(
                "vacuum",
                mean_photon_number=0.0,
                selection_probability=0.1,
            ),
        ),
    ),
)
```

The selection probabilities must sum to 1. Intensity names must be unique.
Vacuum decoys use `mean_photon_number=0.0`.

The asymptotic decoy estimator is controlled from the classical
post-processing configuration:

```python
from qiskit_qkd import PostProcessingConfig

post_processing = PostProcessingConfig(
    decoy_security_estimation_enabled=True,
    decoy_security_method="vacuum_weak_asymptotic",
)
```

Set `decoy_security_estimation_enabled=False` or
`decoy_security_method="none"` when a run should report only observed
per-intensity statistics.

## Source Model

`WeakCoherentDecoySource` samples one intensity class per attempted clock slot.
Then it samples the photon number from a Poisson distribution:

```text
P(n | mu) = exp(-mu) * mu**n / n!
```

An `EmissionEvent` records:

- `intensity_class`: selected class, such as `signal`, `decoy`, or `vacuum`;
- `photon_number`: sampled Poisson photon number;
- `emitted`: true when `photon_number > 0`.

This keeps the source model useful for photon-number-splitting and decoy
estimation.

## Channel Survival

For one emitted photon, the existing channel survival probability is used:

```text
eta_channel = 10 ** (-loss_db / 10)
```

For multi-photon weak-coherent pulses, the channel layer samples the number of
surviving photons rather than collapsing immediately to a boolean:

```text
K_survives ~ Binomial(n, eta_channel)
transmitted = K_survives > 0
```

The simulator still records one threshold-detection opportunity for Bob. It
does not yet model photon-number-resolving detectors or individual photon paths.
The threshold detector then applies its efficiency to the surviving photons:

```text
P(signal click | K_survives) = 1 - (1 - eta_detector)**K_survives
```

Marginally, without dark counts, background light, timing discards, or dead
time, this gives the expected multi-photon gain:

```text
P(signal click | n) = 1 - (1 - eta_channel * eta_detector)**n
```

## Protocol Flow

Decoy state metadata travels through the existing BB84 event flow:

1. The source samples `intensity_class` and `photon_number`.
2. The channel samples `surviving_photon_number`; `transmitted` remains the
   public-style boolean `surviving_photon_number > 0`.
3. Timing assigns that signal to Bob's gate or marks it as an out-of-window
   event.
4. Eve, when configured, acts at `EveConfig.attack_position`. The default
   `post_loss` position sees only surviving, timing-valid signal opportunities;
   `pre_loss` acts after source preparation and before channel survival. Eve
   remains separate from accidental background and detector effects.
5. The threshold detector decides whether Bob records a click.
6. Sifting and classical post-processing use only Alice/Bob public protocol
   data, while `SimulationResult.decoy` keeps simulator-side diagnostics.

This makes decoy behavior tangible without entangling source statistics with
Aer noise, Eve, or reconciliation.

## Result Rows

`SimulationResult.decoy` stores JSON-safe per-intensity statistics:

```text
pulses
selection_fraction
selection_probability
mean_photon_number
emitted
zero_photon
single_photon
multi_photon
surviving_photons
transmitted
detected
sifted
errors
gain
qber
```

These rows are intentionally flat and table-like so they can be plotted or
exported later without parsing event logs.

For plotting, CSV export, or Pandas, use the analysis helper:

```python
from qiskit_qkd import decoy_rows_from_result

rows = decoy_rows_from_result(result)
```

It returns one flat row per intensity plus one optional `row_type="security"`
row when the estimator is enabled.

## Asymptotic Vacuum+Weak Estimator

When the scenario contains one signal intensity, one weak positive decoy, and
one vacuum class, `SimulationResult.decoy["security"]` stores an asymptotic
vacuum+weak estimate.

The estimator chooses:

```text
mu = highest positive mean photon number
nu = next positive mean photon number, with mu > nu > 0
vacuum = intensity with mean photon number 0
```

From the observed gains `Q_mu`, `Q_nu`, and `Y0 = Q_vacuum`, it computes:

```text
Y1_L =
  mu / (mu * nu - nu**2)
  * (
      Q_nu * exp(nu)
      - Q_mu * exp(mu) * nu**2 / mu**2
      - (mu**2 - nu**2) / mu**2 * Y0
    )

Q1_L = mu * exp(-mu) * Y1_L
```

The single-photon error upper bound is:

```text
e1_U = (E_nu * Q_nu * exp(nu) - 0.5 * Y0) / (nu * Y1_L)
```

Bounds are clipped to `[0, 1]` and warnings are recorded when clipping is
needed, which can happen in short Monte Carlo runs. The reported decoy secret
rate uses the observed signal-basis sift factor and the configured
`error_correction_efficiency`:

```text
R_signal =
  q_sift
  * max(0, Q1_L * (1 - h2(e1_U)) - f_ec * Q_mu * h2(E_mu))

secret_key_rate_bps =
  clock_rate_hz * signal_selection_fraction * R_signal
```

In the simulator's BB84 diagnostic model, `E_mu >= 0.5` or `e1_U >= 0.5`
contributes no usable secrecy. This avoids the misleading raw entropy edge case
where `h2(1) == 0` would otherwise make a fully wrong key look cheap to
privacy-amplify.

The security row includes `single_photon_yield_lower_bound`,
`single_photon_gain_lower_bound`, `single_photon_error_rate_upper_bound`,
`secret_fraction_per_signal_pulse`, and `secret_key_rate_bps`.

## Photon-Number-Splitting Eve

PNS is configured as an adversary, not as accidental noise:

```python
from qiskit_qkd import EveConfig

eve = EveConfig(
    kind="photon_number_splitting",
    pns_split_probability=1.0,
    pns_block_single_photon_probability=0.25,
    attack_position="pre_loss",
)
```

For multi-photon pulses, Eve keeps one photon and forwards the same BB84 state
to Bob. She does not introduce basis errors, but she knows the bit whenever the
event becomes sifted. With `attack_position="post_loss"` (the default), the
split is attempted only when at least two photons survived the channel. With
`"pre_loss"`, Eve can split the emitted multi-photon pulse before channel loss
and the channel then samples survival of what she forwards. For single-photon
pulses, optional blocking can mimic loss and makes the attack visible in decoy
gains.

`attack_position` is a discrete placement for this pedagogical model; it does
not expose a composable two-segment Alice--Eve--Bob channel.

PNS event diagnostics include:

```text
eve_action = pns_split | pns_block_single
tags["eve_forwarded_photons"]
tags["eve_photons_kept"]
tags["eve_blocked_signal"]
tags["eve_knows_bit"]
```

## Boundary

The current estimator is asymptotic and diagnostic. It does not include
finite-key security bounds, composable security, coherent attacks,
authentication failure, photon-number-resolving detectors, or detector-control
attacks. Generic sweep summaries may still attach Wilson/Student-t intervals to
observed Monte Carlo proportions or repeat means; those descriptive intervals
must not be confused with finite-key decoy confidence regions.

Dynamic schedules do not yet mutate individual entries inside
`source.decoy_intensities`. Use static decoy classes for Phase 6, or schedule
the scalar `source.mean_photon_number` only for a single-intensity
weak-coherent source.
