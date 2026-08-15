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
    ),
)
```

Available models:

- `EveConfig(kind="none")`: no adversary. This is the default.
- `EveConfig(kind="intercept_resend", intercept_probability=p)`: Eve
  intercepts each surviving signal round with probability `p`, measures in a
  random BB84 basis, then resends the measured bit in that basis.
- `EveConfig(kind="photon_number_splitting", pns_split_probability=p)` or
  `kind="pns"`: Eve splits multi-photon weak-coherent pulses without changing
  the BB84 state. `pns_block_single_photon_probability` optionally blocks
  single-photon pulses to mimic lossy-link attacks.

`intercept_probability` is validated as a probability in `[0, 1]`. The attack
uses the scenario RNG, so repeated runs with the same scenario and backend seed
are reproducible.

## Intercept-Resend Semantics

For each emitted, transmitted, timing-valid signal round:

1. Eve samples whether to intercept.
2. If she intercepts, she chooses one of the protocol bases.
3. If Eve's basis equals Alice's basis, Eve measures Alice's bit exactly and
   resends the same bit and basis.
4. If Eve's basis differs from Alice's basis, Eve obtains a random bit and
   resends that bit in the wrong basis.
5. Bob measures the state that Eve resent.

This gives the standard pedagogical BB84 trend: full intercept-resend attacks
produce about 25% QBER on sifted key bits under ideal lossless conditions.

## Photon-Number-Splitting Semantics

For each emitted, transmitted, timing-valid signal round:

1. Eve receives simulator-side photon-number diagnostics.
2. If the original pulse and the post-channel surviving signal are both
   multi-photon, she keeps one surviving photon with probability
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

The simulator never lets PNS create photons after channel loss. If a
multi-photon pulse reaches the Eve layer with only one surviving photon, the
split branch is skipped and Bob receives that one photon unchanged.

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
