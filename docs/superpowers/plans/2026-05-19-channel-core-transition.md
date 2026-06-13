# Channel-Core Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` to
> implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Reorient `qiskit-qkd` into a single-package Qiskit-first QKD channel
simulator, with protocols such as BB84/E91 layered on top.

**Architecture:** Keep one distributable package. Internally separate protocol
logic from the reusable simulation core: source/emitter, quantum channel,
timing, detector/receiver, classical transcript, Qiskit adapters, and
post-processing. Preserve Phase 3.5 timing behavior as the validated baseline.

**Tech Stack:** Python 3.11+, dataclasses, Qiskit primitives, optional Qiskit
Aer, pytest, ruff.

---

## Implemented Transition

- [x] Added `qiskit_qkd.sources` with `EmissionEvent`,
  `IdealSinglePhotonSource`, and `source_from_config()`.
- [x] Added `qiskit_qkd.channel_core.prepare_physical_round()` to combine
  source emission, channel survival, and timing-gate assignment.
- [x] Refactored BB84 so protocol logic supplies bits and bases while the
  reusable channel core supplies physical source/channel/timing outcomes.
- [x] Preserved the Qiskit boundary: Qiskit is called only for surviving signal
  rounds; losses, no-clicks, dark counts, dead time, afterpulsing, and timing
  remain in the event layer.
- [x] Added Phase 3.6 pedagogical classical post-processing with reproducible
  QBER sampling, block-parity reconciliation diagnostics, `leak_ec`, and
  optional privacy-amplification digest.
- [x] Added `SimulationResult.classical` as the JSON-safe public container for
  post-processing diagnostics.
- [x] Added Phase 4 Aer `NoiseModel` adapters, controlled transpilation, and
  Qiskit/Aer provenance without moving no-click physics out of the event layer.
- [x] Added layered physical noise extensions: source preparation error,
  coherent polarization misalignment, and optical background clicks.
- [x] Added Phase 4.1 dynamic parameter schedules, channel characterization
  rows, and temporal BB84 sweeps for plot-ready analysis data.
- [x] Added Phase 5 BB84 Eve models with `NoEve`, `InterceptResendEve`, event
  traces, and aggregate Eve metrics.
- [x] Added Phase 6 weak-coherent decoy-state source sampling, multi-photon
  channel survival, and per-intensity BB84 statistics.
- [x] Added Phase 6.2 asymptotic vacuum+weak decoy estimates and
  photon-number-splitting Eve traces.
- [x] Added Phase 7 E91 with Bell-pair circuits, CHSH diagnostics, source-pair
  imperfections, and plot-ready Bell rows.
- [x] Added Phase 8 non-fiber optical channel families for deep-space,
  free-space/satellite, and underwater QKD link studies.

## Deferred Roadmap

- [ ] Phase 9: plotting helpers, CLI, presets, JSON export, and static
  dashboard.

## Verification

- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m ruff check .`
