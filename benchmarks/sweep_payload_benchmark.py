"""Reproducible before/after byte benchmark for panel sweep DTOs.

The scientific helper output is serialized as the Wave 0 baseline.  The same
rows are then wrapped by the compact panel DTO (including its plot summary),
so byte reduction and serialization work are directly comparable.  No result
or artifact files are written unless ``--output`` is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from qiskit_qkd.analysis import (
    compact_sweep_payload,
    summarize_metric_rows,
    sweep_scenario_parameter,
)
from qiskit_qkd.config import ChannelConfig, PostProcessingConfig, Scenario
from qiskit_qkd.protocols import BB84Protocol

SEED = 20260812


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def run_case(points: int) -> dict[str, Any]:
    if points < 1:
        raise ValueError("points must be positive")
    scenario = replace(
        Scenario(
            pulses=32,
            clock_rate_hz=1_000_000.0,
            seed=SEED,
            event_sample_size=0,
            post_processing=PostProcessingConfig(qber_abort_threshold=None),
        ),
        channel=ChannelConfig(kind="fiber", distance_km=0.0),
    )
    values = tuple(index * 0.5 for index in range(points))
    protocol_started = time.perf_counter()
    rows = sweep_scenario_parameter(
        BB84Protocol(),
        scenario,
        "channel.distance_km",
        values,
    )
    protocol_s = time.perf_counter() - protocol_started

    baseline_started = time.perf_counter()
    baseline = canonical_bytes(rows)
    baseline_serialization_s = time.perf_counter() - baseline_started

    summary = summarize_metric_rows(
        rows,
        group_by=("channel.distance_km",),
        metrics=("qber", "secret_key_rate_bps", "gain", "detected"),
    )
    compact_started = time.perf_counter()
    compact = compact_sweep_payload(
        rows,
        requested_scenario_digest=scenario.digest(),
        summary=summary,
    )
    compact_build_s = time.perf_counter() - compact_started
    compact_serialization_started = time.perf_counter()
    compact_encoded = canonical_bytes(compact)
    compact_serialization_s = time.perf_counter() - compact_serialization_started

    return {
        "points": points,
        "pulses_per_evaluation": scenario.pulses,
        "seed": SEED,
        "rows": len(rows),
        "protocol_s": protocol_s,
        "baseline_serialization_s": baseline_serialization_s,
        "compact_build_s": compact_build_s,
        "compact_serialization_s": compact_serialization_s,
        "baseline_bytes": len(baseline),
        "compact_bytes": len(compact_encoded),
        "reduction_fraction": 1.0 - len(compact_encoded) / len(baseline),
        "baseline_sha256": hashlib.sha256(baseline).hexdigest(),
        "compact_sha256": hashlib.sha256(compact_encoded).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--points",
        nargs="+",
        type=int,
        default=[256, 4096],
        help="axis point counts (default: 256 4096)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "schema_version": 1,
        "cases": [run_case(points) for points in args.points],
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
