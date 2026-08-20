"""Bounded-memory engine benchmark for the Wave 1 protocol paths.

The benchmark deliberately keeps wall-clock and ``tracemalloc`` runs separate:
starting a tracer perturbs timings, while serializing the result would hide the
peak live-round allocation we want to observe.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import platform
import sys
import time
import tracemalloc
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import qiskit

from qiskit_qkd import (
    E91Config,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.backends import backend_from_scenario
from qiskit_qkd.protocols import BB84Protocol, E91Protocol
from qiskit_qkd.provenance import extract_seeds, scenario_provenance, vcs_provenance

ROOT = Path(__file__).resolve().parents[1]

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
    return runner.run(scenario, backend=backend_from_scenario(scenario))


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
    scenario = _scenario(protocol, pulses)
    return {
        "protocol": protocol,
        "pulses": pulses,
        "wall_s": wall_s,
        "peak_python_mib": peak_bytes / (1024 * 1024),
        "output_sha256": timed_digest,
        "memory_run_matches_timed_run": memory_digest == timed_digest,
        "event_sample_size": len(timed_result.event_sample),
        "scenario": scenario_provenance(scenario),
        "seeds": extract_seeds(scenario),
    }


def _write_csv(report: dict[str, Any], path: Path) -> str:
    fields = [
        "result_id",
        "manifest_ref",
        "protocol",
        "pulses",
        "seed",
        "seed_paths",
        "scenario_digest",
        "wall_s",
        "peak_python_mib",
        "output_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in report["cases"]:
            seeds = row.get("seeds", {})
            writer.writerow(
                {
                    "result_id": row["result_id"],
                    "manifest_ref": path.with_suffix(".json").name,
                    "protocol": row["protocol"],
                    "pulses": row["pulses"],
                    "seed": seeds.get("seed", ""),
                    "seed_paths": json.dumps(seeds, sort_keys=True),
                    "scenario_digest": row["scenario"].get("digest", ""),
                    "wall_s": row["wall_s"],
                    "peak_python_mib": row["peak_python_mib"],
                    "output_sha256": row["output_sha256"],
                }
            )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(
    report: dict[str, Any],
    csv_path: Path | None,
    csv_sha256: str | None,
) -> dict[str, Any]:
    vcs = vcs_provenance(ROOT)
    script = Path(__file__).resolve()
    return {
        "schema_version": 1,
        "generated_at_utc": report["generated_at_utc"],
        "runtime": report["runtime"],
        "git": vcs,
        "commit": vcs.get("commit", "unknown"),
        "commit_confidence": vcs.get("confidence", "none"),
        "commit_verified": vcs.get("commit_verified", False),
        "generator": {
            "path": str(script),
            "sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "command": report["command"],
        },
        "seeds": {row["result_id"]: row["seeds"] for row in report["cases"]},
        "scenarios": [row["scenario"] for row in report["cases"]],
        "csv": {
            "path": str(csv_path) if csv_path else "unknown",
            "sha256": csv_sha256 or "unknown",
            "row_count": len(report["cases"]),
        },
        "results": [
            {
                "result_id": row["result_id"],
                "csv_row": index + 2,
                "scenario_digest": row["scenario"].get("digest", ""),
                "seed_paths": row["seeds"],
            }
            for index, row in enumerate(report["cases"])
        ],
        "result_ids": [row["result_id"] for row in report["cases"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for pulses in (1_024, 4_096):
        rows.append(_measure("bb84", pulses))
    for pulses in (1_024, 4_096, 16_384):
        rows.append(_measure("e91", pulses))
    for index, row in enumerate(rows, start=1):
        row["result_id"] = f"{row['protocol']}-{row['pulses']}-{index:02d}"
    csv_path = args.csv or (args.output.with_suffix(".csv") if args.output else None)
    csv_hash = _write_csv(
        {"cases": rows}, csv_path
    ) if csv_path else None
    try:
        aer_version = metadata.version("qiskit-aer")
    except metadata.PackageNotFoundError:
        aer_version = None
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "seed": SEED,
        "sample_size": SAMPLE_SIZE,
        "runtime": {
            "python": sys.version,
            "python_version": platform.python_version(),
            "qiskit": qiskit.__version__,
            "qiskit_aer": aer_version,
            "qiskit_aer_status": "available" if aer_version else "absent",
        },
        "cases": rows,
    }
    report["manifest"] = _manifest(report, csv_path, csv_hash)
    encoded = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    elif csv_path:
        csv_path.with_suffix(".json").write_text(encoded, encoding="utf-8")
        print(f"Benchmark manifest: {csv_path.with_suffix('.json')}")
    else:
        print(encoded)


if __name__ == "__main__":
    main()
