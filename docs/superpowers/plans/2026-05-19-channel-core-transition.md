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

## Deferred Roadmap

- [ ] Phase 4: Eve BB84 with `NoEve` and `InterceptResendEve`.
- [ ] Phase 5: decoy BB84 with weak coherent sources and per-intensity stats.
- [ ] Phase 6: Aer `NoiseModel` adapters and transpilation options.
- [ ] Phase 7: E91 with Bell-pair circuits and CHSH.
- [ ] Phase 8: CLI, presets, JSON export, and static dashboard.

## Verification

- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m ruff check .`
