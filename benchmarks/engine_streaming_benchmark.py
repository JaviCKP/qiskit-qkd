"""Bounded-memory engine benchmark for the Wave 1 protocol paths.

The benchmark deliberately keeps wall-clock and ``tracemalloc`` runs separate:
starting a tracer perturbs timings, while serializing the result would hide the
peak live-round allocation we want to observe.
"""

from __future__ import annotations

import gc
import hashlib
import json
import time
import tracemalloc
from typing import Any

from qiskit_qkd import (
    E91Config,
    PostProcessingConfig,
    ProtocolConfig,
    QiskitSamplerBackend,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.protocols import BB84Protocol, E91Protocol

SEED = 20260812
SAMPLE_SIZE = 16


def _scenario(protocol: str, pulses: int) -> Scenario:
    if protocol == "e91":
        return Scenario(
            pulses=pulses,
            clock_rate_hz=1_000_000.0,
            seed=SEED,
            protocol=ProtocolConfig(name="e91"),
            source=SourceConfig(kind="entangled_pair"),
            e91=E91Config(),
            event_sample_size=SAMPLE_SIZE,
            post_processing=PostProcessingConfig(qber_abort_threshold=None),
        )
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=SEED,
        event_sample_size=SAMPLE_SIZE,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )


def _run(protocol: str, pulses: int) -> Any:
    scenario = _scenario(protocol, pulses)
    runner = E91Protocol() if protocol == "e91" else BB84Protocol()
    return runner.run(
        scenario,
        backend=QiskitSamplerBackend(seed=SEED),
    )


def _digest(result: Any) -> str:
    payload = json.dumps(
        result.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _measure(protocol: str, pulses: int) -> dict[str, Any]:
    # Warmup and wall-clock run are intentionally untraced.
    _run(protocol, 64)
    gc.collect()
    started = time.perf_counter()
    timed_result = _run(protocol, pulses)
    wall_s = time.perf_counter() - started

    # A fresh run under tracemalloc isolates peak Python allocations.
    gc.collect()
    tracemalloc.start()
    try:
        memory_result = _run(protocol, pulses)
        _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    timed_digest = _digest(timed_result)
    memory_digest = _digest(memory_result)
    return {
        "protocol": protocol,
        "pulses": pulses,
        "wall_s": wall_s,
        "peak_python_mib": peak_bytes / (1024 * 1024),
        "output_sha256": timed_digest,
        "memory_run_matches_timed_run": memory_digest == timed_digest,
        "event_sample_size": len(timed_result.event_sample),
    }


def main() -> None:
    rows: list[dict[str, Any]] = []
    for pulses in (1_024, 4_096):
        rows.append(_measure("bb84", pulses))
    for pulses in (1_024, 4_096, 16_384):
        rows.append(_measure("e91", pulses))
    print(
        json.dumps(
            {"seed": SEED, "sample_size": SAMPLE_SIZE, "cases": rows},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
