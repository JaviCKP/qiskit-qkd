# Eavesdropping Models

Phase 5 adds explicit adversarial models for BB84. Phase 6.2 extends that
layer with photon-number-splitting for weak-coherent decoy scenarios. These
models are separate from accidental noise: detector dark counts, optical
background, timing jitter, and Aer state noise remain physical or
quantum-channel effects, while Eve is a named actor whose actions are recorded
on events and metrics.

## Core API

Configure Eve on the scenario:

```python
from qiskit_qkd import EveConfig, Scenario

scenario = Scenario(
    pulses=2_048,
    clock_rate_hz=1_000_000.0,
    seed=53,
    eavesdropper=EveConfig(
        kind="intercept_resend",
        intercept_probability=1.0,
        attack_position="post_loss",
    ),
)
```

Available models:

- `EveConfig(kind="none")`: no adversary. This is the default.
- `EveConfig(kind="intercept_resend", intercept_probability=p)`: Eve
  intercepts a signal opportunity with probability `p`, measures in a random
  BB84 basis, then resends the measured bit in that basis.
- `EveConfig(kind="photon_number_splitting", pns_split_probability=p)` or
  `kind="pns"`: Eve splits multi-photon weak-coherent pulses without changing
  the BB84 state. `pns_block_single_photon_probability` optionally blocks
  single-photon pulses to mimic lossy-link attacks.

`attack_position` is a discrete choice with values `post_loss` (the default)
and `pre_loss`. In the pedagogical default, channel survival and timing are
sampled first; Eve then receives only a surviving, timing-valid signal. With
`pre_loss`, Eve acts after source preparation but before channel survival, so a
PNS attack can inspect the emitted photon number and choose how many photons to
forward. This is one explicit placement seam, not an arbitrary composable
two-segment channel model.

`intercept_probability` is validated as a probability in `[0, 1]`. The attack
uses the scenario RNG, so repeated runs with the same scenario and backend seed
are reproducible.

The protocol creates a `PreparedState` before invoking Eve. It records Alice's
logical bit, the sampled preparation error, and the physical bit sent into the
attack/channel path. Eve therefore receives the physical prepared bit; the
logical bit is retained for sifting and diagnostics.

## Intercept-Resend Semantics

For each signal round presented to Eve at the configured position:

1. Eve samples whether to intercept.
2. If she intercepts, she chooses one of the protocol bases.
3. If Eve's basis equals Alice's basis, Eve measures the physical prepared bit
   exactly and
   resends the same bit and basis.
4. If Eve's basis differs from Alice's basis, Eve obtains a random bit and
   resends that bit in the wrong basis.
5. Bob measures the state that Eve resent.

This gives the standard pedagogical BB84 trend: full intercept-resend attacks
produce about 25% QBER on sifted key bits under ideal lossless conditions.

## Photon-Number-Splitting Semantics

For each signal round presented to Eve at the configured position:

1. Eve receives simulator-side photon-number diagnostics.
2. In `post_loss`, the split branch requires the post-channel surviving count
   to be multi-photon; in `pre_loss`, Eve can split the emitted multi-photon
   pulse before the channel samples loss. She keeps one photon with probability
   `pns_split_probability`.
3. She forwards the same BB84 state to Bob, so the split itself does not add
   basis errors.
4. If the event is later sifted, Eve is counted as knowing Alice's bit because
   she can wait for public basis announcement.
5. If `photon_number == 1`, she may block the signal with probability
   `pns_block_single_photon_probability`.

Single-photon blocking is optional. It is useful for experiments where Eve
tries to hide inside channel loss while preserving information from
multi-photon pulses.

In the default `post_loss` model, PNS never creates photons after channel loss:
if only one photon survives, the split branch is skipped and Bob receives that
one photon unchanged. Selecting `pre_loss` is the explicit stronger placement
for experiments that need Eve to act before loss; it still does not introduce
a general pair of independently configurable channel segments.

## Traceability

Eve diagnostics are stored per event:

- `eve_action`: `intercept_resend`, `pns_split`, or `pns_block_single`.
- `eve_basis`: Eve's measurement and resend basis.
- `eve_detectable`: true when Eve used a basis different from Alice's basis,
  meaning the action can introduce detectable disturbance.
- `tags["eve_bit"]`: Eve's measured bit.
- `tags["eve_resend_bit"]` and `tags["eve_resend_basis"]`: the state sent to
  Bob.
- `tags["eve_knows_bit"]`: true when Eve used Alice's basis and therefore
  knows the sifted bit if that event survives sifting. For PNS splits this is
  true because Eve keeps a photon and waits for basis announcement.
- `tags["eve_forwarded_photons"]`: photons forwarded after a PNS split or
  block.
- `tags["eve_photons_kept"]`: photons retained by Eve in a PNS split.
- `tags["eve_blocked_signal"]`: true when Eve blocks a single-photon signal.

Aggregate metrics include:

- `eve_intercepted_fraction`: intercepted signal rounds divided by transmitted
  signal rounds.
- `eve_information_estimate`: fraction of sifted bits for which the simulator
  knows Eve used Alice's basis.

These diagnostics are simulator-side validation aids. Alice and Bob do not get
to use hidden event fields during sifting or reconciliation.

## Boundary

The Eve layer currently includes `NoEve`, `InterceptResendEve`, and
`PhotonNumberSplittingEve`. It does not implement coherent attacks,
authenticated-channel failure, detector-control attacks, or composable
finite-key proofs. Those belong to later protocol/security phases.
