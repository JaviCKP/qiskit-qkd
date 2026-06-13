# Examples

This directory contains small executable examples.

- `bb84_ideal.py`: runs ideal BB84 through real Qiskit circuits and prints a
  `SimulationResult` summary plus the first circuit.
- `bb84_fiber_sweep.py`: runs BB84 over a fiber channel for several distances
  and prints a compact table of loss, detections, gain, QBER, and secret rate.
- `bb84_visualization.py`: with the optional `plot` extra installed, saves a
  BB84 distance-sweep SVG figure under `examples/figures/`; without the extra,
  prints the installation hint and exits successfully.
- `bb84_aer_noisy.py`: compares ideal BB84 with Aer depolarizing,
  phase-damping, and readout-noise scenarios while keeping no-click physics in
  the event layer.
- `bb84_physical_noise.py`: compares ideal BB84 with source preparation
  errors, coherent polarization misalignment, and optical background clicks.
- `bb84_dynamic_channel.py`: samples dynamic Phase 4.1 communication
  conditions over selected times and prints plot-ready BB84 comparison rows.
- `bb84_eve_intercept_resend.py`: compares BB84 without Eve against partial
  and full intercept-resend attacks, reporting QBER and Eve trace metrics.
- `bb84_decoy.py`: runs BB84 with weak-coherent `signal`, `decoy`, and
  `vacuum` intensities, prints per-intensity statistics, and reports the
  asymptotic vacuum+weak decoy estimate plus the available plot-ready rows.
- `e91_chsh.py`: runs E91 with a singlet Bell pair, prints CHSH, key QBER,
  and per-setting correlations, then compares against a noisy pair source.

Fiber PMD/CD, PDL, and Raman parameters are configured through `ChannelConfig`
and are easiest to inspect with `ChannelCharacterizer` or temporal sweeps.
Space, free-space/satellite, and underwater channels use the same
`ChannelConfig` plus `ChannelCharacterizer` path; see
`docs/optical_channels.md` for their formulas and fields.
Optional Phase 9 figures are documented in `docs/visualization.md`.
