# Qiskit And Aer Integration

Phase 4 makes the Qiskit boundary explicit. Qiskit owns inspectable circuits,
primitive execution, optional transpilation, and Aer noise that acts on a
surviving quantum state. The QKD event layer still owns photonic effects that
create no-clicks or detector events.

## Modeling Boundary

| Phenomenon | Implementation |
| --- | --- |
| Fiber attenuation and fixed optical loss | Event-layer Monte Carlo transmission/no-click |
| Space/free-space/underwater geometric and medium loss | Event-layer channel transmittance |
| Scintillation and pointing jitter | Event-layer pulse-level `sample_transmittance(rng)` |
| Underwater scattering broadening | Event-layer timing broadening and gate assignment |
| BB84 polarization-dependent loss | Event-layer state-dependent transmittance before circuit execution |
| PMD and chromatic dispersion | Event-layer timing broadening and gate assignment |
| Raman crosstalk | Event-layer effective optical background rate |
| Detector efficiency | Event-layer detector sampling |
| Dark counts, double clicks, dead time, afterpulsing | Event-layer detector state |
| Timing gates, jitter, clock offset/drift | Event-layer timing metadata |
| Decoy intensity and photon-number sampling | Event-layer source sampling |
| BB84 preparation and basis changes | `CircuitFactory` and `QuantumCircuit` |
| E91 Bell-pair preparation and angular measurements | `CircuitFactory.e91_bell_measure()` |
| Source preparation error | Sampled once into `PreparedState` before Eve/channel processing; physical bit is encoded |
| E91 Bell-pair preparation error | Sampled Pauli error on Bob's Bell-pair qubit |
| Coherent polarization misalignment | Explicit `ry`/`rz` gates in the BB84 circuit |
| Channel depolarization | Aer `depolarizing_error` on the circuit channel marker |
| Channel dephasing | Aer `phase_damping_error` on the circuit channel marker |
| Optical background photons | Event-layer random detector clicks with `detection_origin="background"` |
| Readout error | Aer `ReadoutError` on measurement |
| Dynamic parameter schedules | `ParameterResolver` creates static effective scenarios before execution |
| Eve intercept-resend actions | BB84 adversarial layer before Bob's measurement |
| Eve photon-number-splitting actions | BB84 adversarial layer using source photon-number diagnostics |
| Sifting, QBER sampling, reconciliation, privacy amplification | Classical post-processing |

The BB84 circuit includes one explicit `id` instruction after Alice's
preparation and before Bob's basis change. Phase 4 uses that instruction as the
Aer channel marker. This keeps channel state noise visible in the circuit while
preventing fiber loss from being represented as a fake measured bit.

Preparation errors are sampled before circuit construction and stored in a
`PreparedState` that keeps Alice's logical bit separate from the physical bit
encoded in the circuit. The order is logical bit → preparation error → physical
prepared state → Eve (at `attack_position`) → channel → Bob. Coherent
polarization misalignment is represented by explicit `ry`/`rz` gates after the
channel marker and before Bob's basis change. These are intentionally
inspectable circuit effects, not classical post-processing shortcuts. PDL uses
the physical prepared bit when sampling state-dependent survival.

Weak-coherent decoy behavior also stays outside Aer. The source chooses an
intensity class and samples a Poisson photon number before the channel layer
samples how many photons survive. The detector then applies efficiency to that
surviving count. Qiskit still receives one BB84 state only for surviving
threshold-detection opportunities; it does not model the Poisson source
distribution or photon-number-resolving behavior.

Phase 6.1 fiber impairments follow the same boundary. PDL changes the
Monte-Carlo survival probability for the prepared BB84 state, PMD and
chromatic dispersion broaden the arrival-time distribution used by the timing
layer, and Raman crosstalk increases the background-count rate seen by the
detector. None of these are added as Aer `NoiseModel` operations.

Phase 7 E91 uses the same Qiskit boundary. The circuit prepares a Bell pair,
applies an optional source-pair Pauli error, marks Bob's channel with `id`,
applies coherent Bob-channel rotations, and measures Alice/Bob in configured
angular settings. Bob-arm loss, no-clicks, timing gates, detector efficiency,
dark/background clicks, dead time, and afterpulsing remain event-layer effects.
Alice's local detector does not receive Bob-arm Raman/background counts. E91
does not reuse the BB84 classical PDL approximation because Bob's entangled
photon does not carry a pre-measurement classical polarization label.

Phase 8 non-fiber channels also stay outside Aer. Space, free-space, and
underwater media decide whether photons survive and how timing broadening
changes Bob's gate assignment. Depolarization, dephasing, and coherent
polarization rotations remain explicit Qiskit/Aer configuration.

## API

When a `Scenario` sets `channel.depolarizing_probability`,
`channel.phase_damping_probability`, or `detector.readout_error_probability`,
the default BB84/E91 runner builds an Aer-backed `QiskitSamplerBackend`
automatically. Callers only need to pass a backend when they want custom
transpilation, custom shots, or an externally managed sampler.

```python
from qiskit_qkd import ChannelConfig, Scenario
from qiskit_qkd.protocols import BB84Protocol

scenario = Scenario(
    pulses=512,
    clock_rate_hz=1_000_000.0,
    seed=7,
    channel=ChannelConfig(depolarizing_probability=0.25),
)

result = BB84Protocol().run(scenario)
print(result.metrics.qber)
print(result.qiskit["noise_model"])
```

`backend_from_scenario(scenario)` is the canonical constructor used by BB84 and
E91. It selects an ideal sampler or builds `AerNoiseModelAdapter`, passes the
resulting `NoiseModel`, configures scenario seeds and transpilation, and returns
the ready backend. Experiment scripts should use this factory instead of
recreating Aer/seed/transpilation wiring. A supplied custom backend is accepted
only when its Aer/no-Aer boundary and noise signature match the scenario: a
scenario with Aer state/readout noise is rejected if the backend has no
`noise_model` or uses a non-Aer sampler, while an ideal scenario is rejected if
the supplied backend carries a noise model. Reusing a backend configured for a
different scenario noise signature is also rejected; create a fresh backend or
let the factory build one.

`SimulationResult.qiskit` records the primitive name, Qiskit and Aer versions,
shots, seeds, circuit-count metadata, counts samples, transpilation settings,
and a compact noise-model summary.

When Aer quantum channel noise is attached to the explicit `id` channel marker,
optimization levels above `0` may remove that marker. The backend therefore
uses effective optimization level `0` for those noisy circuits and records the
requested level under `requested_optimization_level`.

For the default noiseless backend, when no external sampler, transpilation, or
Aer noise model is provided, `QiskitSamplerBackend` still builds the same
inspectable circuits but samples the final Qiskit `Statevector` probabilities
directly with its own seeded RNG. This keeps partial rotations statistically
faithful with one shot per physical round. Primitive execution is used whenever
the caller supplies a sampler, transpilation, or Aer noise. Scenario-level Aer
noise fields count as Aer noise even when no backend argument is passed.

## Validation Expectations

Phase 4 tests check that:

- depolarizing noise increases BB84 QBER relative to the ideal backend;
- full phase damping leaves Z-basis measurements stable while randomizing
  X-basis coherence;
- readout error flips a trivial BB84 measurement when configured at `1.0`;
- transpilation preserves circuit metadata and records its seed/options;
- fiber loss, no-clicks, detector efficiency, dark counts, dead time,
  optical background, afterpulsing, and timing gates do not enter the Aer
  `NoiseModel`;
- source preparation errors and coherent polarization misalignment affect the
  measured signal bits before sifting.

This is a simulation of the detectable quantum-state part of the channel, not a
claim that Aer alone models a full photonic QKD link.

Phase 4.1 dynamic schedules do not change this boundary. They resolve ordinary
scenario fields at selected `time_s` values before a protocol run or channel
characterization pass. Aer still receives only the effective static parameters
for the specific run being executed.

Phase 5/6.2 Eve models also stay outside Aer. Intercept-resend is modeled as
an explicit adversarial measurement and resend of a BB84 state before Bob's
measurement. PNS is modeled as an adversarial photon-number action before Bob's
measurement. `EveConfig.attack_position="post_loss"` (default) places that
action after channel survival/timing, while `"pre_loss"` places it after
`PreparedState` and before channel survival. Neither is an accidental
`NoiseModel` component; the position is a discrete pedagogical seam rather
than a composable two-segment channel.

Phase 6 decoy-state source statistics follow the same separation. They alter
which physical events reach Bob and how those events are summarized, but they
do not add Aer `NoiseModel` errors and they do not change the BB84 circuit
interface. Phase 6.2 decoy security estimates are classical post-processing
over those event-layer statistics.

Phase 6.1 fiber impairments also stay out of Aer. They are photonic link and
receiver effects that alter loss, timing validity, or background clicks before
and after the circuit path.

Phase 7 E91 also stays inside this boundary. Aer depolarizing, phase damping,
and readout noise can degrade Bell correlations directly from scenario config
fields; passing a backend remains available for custom execution settings.

Phase 8 channel families preserve that rule. Atmospheric turbulence,
pointing jitter, and underwater scattering are not Aer errors; they are
link-budget and timing effects in the event layer.
