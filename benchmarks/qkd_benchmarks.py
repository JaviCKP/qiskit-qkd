"""Bounded, reproducible benchmarks for the QKD engine and panel workloads."""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib.util
import json
import platform
import random
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import qiskit

from qiskit_qkd.analysis import sweep_scenario_parameter
from qiskit_qkd.backends import QiskitSamplerBackend, backend_from_scenario
from qiskit_qkd.config import (
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    E91Config,
    PostProcessingConfig,
    ProtocolConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.protocols import BB84Protocol, E91Protocol
from qiskit_qkd.provenance import (
    extract_seeds,
    scenario_provenance,
    vcs_provenance,
)
from qiskit_qkd.sources import WeakCoherentDecoySource

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPEATS = 5
DEFAULT_WARMUPS = 1
WORKLOAD_VERSION = 1


@dataclass(slots=True)
class ExecutionCounters:
    quantum_s: float = 0.0
    circuits: int = 0
    shots: int = 0


class TimedBackend:
    """Delegate to Qiskit while recording only the measurement boundary."""

    def __init__(self, backend: QiskitSamplerBackend, counters: ExecutionCounters):
        self._backend = backend
        self._counters = counters

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)

    def measure_bb84_batch(
        self,
        rounds: Sequence[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        return self._measure(self._backend.measure_bb84_batch, rounds)

    def measure_e91_batch(
        self,
        rounds: Sequence[tuple[float, float, str]],
    ) -> tuple[tuple[int, int], ...]:
        return self._measure(self._backend.measure_e91_batch, rounds)

    def _measure(self, fn: Callable[[Any], Any], rounds: Sequence[Any]) -> Any:
        circuits_before = self._backend.circuit_count
        shots_before = sum(self._backend.counts_by_outcome.values())
        started = time.perf_counter()
        result = fn(rounds)
        self._counters.quantum_s += time.perf_counter() - started
        self._counters.circuits += self._backend.circuit_count - circuits_before
        self._counters.shots += (
            sum(self._backend.counts_by_outcome.values()) - shots_before
        )
        return result


@dataclass(frozen=True, slots=True)
class Workload:
    execute: Callable[[], Any]
    counters: ExecutionCounters
    events_processed: int
    scenario: Scenario | None = None


@dataclass(frozen=True, slots=True)
class CaseSpec:
    name: str
    size: str
    description: str
    build: Callable[[], Workload]
    available: Callable[[], bool] = lambda: True


def _timed_backend(
    scenario: Scenario,
    counters: ExecutionCounters,
) -> TimedBackend:
    backend = backend_from_scenario(scenario)
    backend.max_recorded_results = 0
    return TimedBackend(backend, counters)


def _single_protocol_workload(
    scenario_factory: Callable[[], Scenario],
    protocol_factory: Callable[[], BB84Protocol | E91Protocol],
) -> Workload:
    scenario = scenario_factory()
    counters = ExecutionCounters()
    backend = _timed_backend(scenario, counters)
    protocol = protocol_factory()
    return Workload(
        execute=lambda: protocol.run(scenario, backend=backend),
        counters=counters,
        events_processed=scenario.pulses,
        scenario=scenario,
    )


def _base_scenario(*, pulses: int, seed: int = 20260809) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        event_sample_size=16,
    )


def _bb84_ideal() -> Workload:
    return _single_protocol_workload(
        lambda: _base_scenario(pulses=1_024),
        BB84Protocol,
    )


def _bb84_channel_detector() -> Workload:
    def scenario() -> Scenario:
        return replace(
            _base_scenario(pulses=1_024, seed=20260810),
            channel=ChannelConfig(
                kind="fiber",
                distance_km=25.0,
                attenuation_db_km=0.2,
                background_count_rate_hz=1_000.0,
            ),
            detector=DetectorConfig(
                efficiency=0.72,
                dark_count_rate_hz=100.0,
                gate_width_s=1e-9,
            ),
        )

    return _single_protocol_workload(scenario, BB84Protocol)


def _bb84_decoy() -> Workload:
    def scenario() -> Scenario:
        return replace(
            _base_scenario(pulses=2_048, seed=20260811),
            source=SourceConfig(
                kind="weak_coherent",
                decoy_intensities=(
                    DecoyIntensity("signal", 0.6, 0.70),
                    DecoyIntensity("decoy", 0.2, 0.20),
                    DecoyIntensity("vacuum", 0.0, 0.10),
                ),
            ),
        )

    return _single_protocol_workload(scenario, BB84Protocol)


def _e91() -> Workload:
    def scenario() -> Scenario:
        return Scenario(
            pulses=768,
            clock_rate_hz=1_000_000.0,
            seed=20260812,
            protocol=ProtocolConfig(name="e91"),
            source=SourceConfig(kind="entangled_pair"),
            e91=E91Config(),
            post_processing=PostProcessingConfig(qber_abort_threshold=None),
            event_sample_size=16,
        )

    return _single_protocol_workload(scenario, E91Protocol)


def _sweep_one_axis() -> Workload:
    scenario = replace(
        _base_scenario(pulses=192, seed=20260813),
        channel=ChannelConfig(kind="fiber", distance_km=0.0),
    )
    values = (0.0, 20.0, 40.0, 60.0)
    counters = ExecutionCounters()

    def execute() -> Any:
        return sweep_scenario_parameter(
            BB84Protocol(),
            scenario,
            "channel.distance_km",
            values,
            backend_factory=lambda item: _timed_backend(item, counters),
        )

    return Workload(
        execute=execute,
        counters=counters,
        events_processed=scenario.pulses * len(values),
        scenario=scenario,
    )


def _sweep_series_repeats() -> Workload:
    scenario = replace(
        _base_scenario(pulses=128, seed=20260814),
        channel=ChannelConfig(kind="fiber", distance_km=0.0),
    )
    axis_values = (0.0, 30.0, 60.0)
    series_values = (0.60, 0.90)
    repeats = 2
    counters = ExecutionCounters()

    def execute() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for efficiency in series_values:
            series_scenario = replace(
                scenario,
                detector=replace(scenario.detector, efficiency=efficiency),
            )
            series_rows = sweep_scenario_parameter(
                BB84Protocol(),
                series_scenario,
                "channel.distance_km",
                axis_values,
                repeats=repeats,
                backend_factory=lambda item: _timed_backend(item, counters),
            )
            for row in series_rows:
                row["detector.efficiency"] = efficiency
            rows.extend(series_rows)
        return rows

    evaluations = len(axis_values) * len(series_values) * repeats
    return Workload(
        execute=execute,
        counters=counters,
        events_processed=scenario.pulses * evaluations,
        scenario=scenario,
    )


def _statevector_batch() -> Workload:
    scenario = _base_scenario(pulses=2_048, seed=20260815)
    counters = ExecutionCounters()
    backend = _timed_backend(scenario, counters)
    backend.configure_from_scenario(scenario)
    states = ((0, "Z", "Z"), (1, "Z", "X"), (0, "X", "Z"), (1, "X", "X"))
    rounds = tuple(states[index % len(states)] for index in range(scenario.pulses))
    return Workload(
        execute=lambda: backend.measure_bb84_batch(rounds),
        counters=counters,
        events_processed=len(rounds),
        scenario=scenario,
    )


def _aer_noise() -> Workload:
    def scenario() -> Scenario:
        return replace(
            _base_scenario(pulses=128, seed=20260816),
            channel=ChannelConfig(depolarizing_probability=0.05),
        )

    return _single_protocol_workload(scenario, BB84Protocol)


def _poisson_large_mean() -> Workload:
    samples = 1_000
    rng = random.Random(20260817)
    source = WeakCoherentDecoySource(
        intensities=(DecoyIntensity("stress", 1_000.0, 1.0),),
    )

    def execute() -> list[int]:
        return [
            source.emit(rng=rng, time_s=index * 1e-9).photon_number
            for index in range(samples)
        ]

    return Workload(
        execute=execute,
        counters=ExecutionCounters(),
        events_processed=samples,
        scenario=Scenario(
            pulses=samples,
            clock_rate_hz=1_000_000.0,
            seed=20260817,
            source=SourceConfig(
                kind="weak_coherent",
                decoy_intensities=(DecoyIntensity("stress", 1_000.0, 1.0),),
            ),
            post_processing=PostProcessingConfig(qber_abort_threshold=None),
        ),
    )


CASES = (
    CaseSpec("bb84_ideal", "medium", "Ideal BB84 protocol run", _bb84_ideal),
    CaseSpec(
        "bb84_channel_detector",
        "medium",
        "BB84 with fiber loss, background, and detector effects",
        _bb84_channel_detector,
    ),
    CaseSpec("bb84_decoy", "medium", "Weak-coherent decoy BB84", _bb84_decoy),
    CaseSpec("e91", "medium", "E91 Bell-pair protocol run", _e91),
    CaseSpec("sweep_one_axis", "small", "Four-point distance sweep", _sweep_one_axis),
    CaseSpec(
        "sweep_series_repeats",
        "medium",
        "Distance sweep with detector series and repeated seeds",
        _sweep_series_repeats,
    ),
    CaseSpec(
        "statevector_no_noise",
        "medium",
        "Repeated equivalent noiseless Statevector circuits",
        _statevector_batch,
    ),
    CaseSpec(
        "aer_noise",
        "small",
        "Aer depolarizing-noise BB84",
        _aer_noise,
        available=lambda: importlib.util.find_spec("qiskit_aer") is not None,
    ),
    CaseSpec(
        "poisson_large_mean",
        "medium",
        "Weak-coherent Poisson source at mean photon number 1000",
        _poisson_large_mean,
    ),
)


def _canonical_json(value: Any) -> str:
    to_dict = getattr(value, "to_dict", None)
    payload = to_dict() if callable(to_dict) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _run_sample(case: CaseSpec, *, track_memory: bool) -> dict[str, Any]:
    gc.collect()
    if track_memory:
        tracemalloc.start()
    build_started = time.perf_counter()
    workload = case.build()
    scenario_build_s = time.perf_counter() - build_started
    run_started = time.perf_counter()
    output = workload.execute()
    protocol_s = time.perf_counter() - run_started
    serialization_started = time.perf_counter()
    serialized = _canonical_json(output)
    serialization_s = time.perf_counter() - serialization_started
    peak_bytes = tracemalloc.get_traced_memory()[1] if track_memory else 0
    if track_memory:
        tracemalloc.stop()
    quantum_s = workload.counters.quantum_s
    scenario_payload = (
        scenario_provenance(workload.scenario)
        if workload.scenario is not None
        else None
    )
    return {
        "scenario_build_s": scenario_build_s,
        "protocol_s": protocol_s,
        "quantum_s": quantum_s,
        "classical_s": max(0.0, protocol_s - quantum_s),
        "serialization_s": serialization_s,
        "total_s": scenario_build_s + protocol_s + serialization_s,
        "peak_python_mib": peak_bytes / (1024 * 1024),
        "circuits": workload.counters.circuits,
        "shots": workload.counters.shots,
        "events_processed": workload.events_processed,
        "output_bytes": len(serialized.encode("utf-8")),
        "output_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "scenario": scenario_payload,
        "seeds": (
            extract_seeds(workload.scenario)
            if workload.scenario is not None
            else {}
        ),
    }


def _aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_keys = (
        "scenario_build_s",
        "protocol_s",
        "quantum_s",
        "classical_s",
        "serialization_s",
        "total_s",
        "peak_python_mib",
    )
    aggregate: dict[str, Any] = {}
    for key in numeric_keys:
        values = [float(sample[key]) for sample in samples]
        mean = statistics.fmean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        aggregate[key] = {
            "median": statistics.median(values),
            "mean": mean,
            "stdev": stdev,
            "min": min(values),
            "max": max(values),
            "relative_stdev_percent": 0.0 if mean == 0.0 else 100.0 * stdev / mean,
        }
    for key in ("circuits", "shots", "events_processed", "output_bytes"):
        values = {int(sample[key]) for sample in samples}
        aggregate[key] = values.pop() if len(values) == 1 else sorted(values)
    digests = {str(sample["output_sha256"]) for sample in samples}
    aggregate["output_sha256"] = digests.pop() if len(digests) == 1 else sorted(digests)
    return aggregate


def _primary_seed(seeds: Any) -> Any:
    """Return the scenario seed for compact CSV, retaining full paths too."""

    if not isinstance(seeds, dict):
        return ""
    for key in ("seed", "scenario.seed"):
        if key in seeds:
            return seeds[key]
    return ""


def _git_value(arguments: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def _environment() -> dict[str, Any]:
    aer_version = None
    if importlib.util.find_spec("qiskit_aer") is not None:
        import qiskit_aer

        aer_version = qiskit_aer.__version__
    status = _git_value(["status", "--short"])
    vcs = vcs_provenance(ROOT)
    return {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "qiskit": qiskit.__version__,
        "qiskit_aer": aer_version,
        "git_revision": _git_value(["rev-parse", "HEAD"]),
        "git_dirty": bool(status),
        "git_provenance": vcs,
    }


def _workload_fingerprint(cases: Sequence[CaseSpec]) -> str:
    payload = {
        "version": WORKLOAD_VERSION,
        "cases": [
            {"name": case.name, "size": case.size, "description": case.description}
            for case in cases
        ],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# QKD benchmark report",
        "",
        f"Workload fingerprint: `{report['workload_fingerprint']}`",
        "",
        "| Case | Median total (s) | RSD | Peak Python MiB | "
        "Circuits | Shots | Events |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in report["cases"]:
        aggregate = case["aggregate"]
        total = aggregate["total_s"]
        lines.append(
            "| {name} | {time:.6f} | {rsd:.2f}% | {memory:.3f} | {circuits} | "
            "{shots} | {events} |".format(
                name=case["name"],
                time=total["median"],
                rsd=total["relative_stdev_percent"],
                memory=aggregate["peak_python_mib"]["median"],
                circuits=aggregate["circuits"],
                shots=aggregate["shots"],
                events=aggregate["events_processed"],
            )
        )
    if report["skipped"]:
        lines.extend(["", "Skipped: " + ", ".join(report["skipped"])])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(report: dict[str, Any], path: Path) -> None:
    """Write one compact, machine-readable row per benchmark case.

    ``result_id`` and ``manifest_ref`` are deliberately redundant with the
    JSON report: a CSV row must remain traceable when copied out of the report.
    """

    fields = [
        "generated_at_utc",
        "script",
        "result_id",
        "manifest_ref",
        "case",
        "size",
        "repeats",
        "seed_paths",
        "seed",
        "scenario_digest",
        "total_median_s",
        "total_stdev_s",
        "events_processed",
        "circuits",
        "shots",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for case in report["cases"]:
            aggregate = case["aggregate"]
            samples = case.get("samples", [])
            first = samples[0] if samples else {}
            scenario = first.get("scenario") or {}
            writer.writerow(
                {
                    "generated_at_utc": report["generated_at_utc"],
                    "script": report["script"],
                    "result_id": case["name"],
                    "manifest_ref": path.with_suffix(".json").name,
                    "case": case["name"],
                    "size": case["size"],
                    "repeats": report["repeats"],
                    "seed_paths": json.dumps(first.get("seeds", {}), sort_keys=True),
                    "seed": _primary_seed(first.get("seeds", {})),
                    "scenario_digest": scenario.get("digest", ""),
                    "total_median_s": aggregate["total_s"]["median"],
                    "total_stdev_s": aggregate["total_s"]["stdev"],
                    "events_processed": aggregate["events_processed"],
                    "circuits": aggregate["circuits"],
                    "shots": aggregate["shots"],
                }
            )


def _benchmark_manifest(
    report: dict[str, Any],
    *,
    csv_path: Path | None,
    csv_sha256: str | None,
    csv_row_count: int,
) -> dict[str, Any]:
    """Return the strict provenance envelope for a persisted benchmark run."""

    script_path = Path(__file__).resolve()
    vcs = vcs_provenance(ROOT)
    aer = report["environment"].get("qiskit_aer")
    scenarios: dict[str, dict[str, Any]] = {}
    seeds: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for case in report["cases"]:
        samples = case.get("samples", [])
        first = samples[0] if samples else {}
        scenario = first.get("scenario") or {}
        digest = scenario.get("digest", "")
        if digest:
            scenarios[digest] = scenario
        case_seeds = {
            key: value
            for sample in samples
            for key, value in sample.get("seeds", {}).items()
        }
        seeds[case["name"]] = dict(sorted(case_seeds.items()))
        results.append(
            {
                "result_id": case["name"],
                "csv_row": len(results) + 2,
                "scenario_digest": digest,
                "seed_paths": seeds[case["name"]],
                "sample_result_ids": [
                    sample.get("result_id", f"{case['name']}-repeat-{index + 1}")
                    for index, sample in enumerate(samples)
                ],
            }
        )
    generated_at = report["generated_at_utc"]
    return {
        "schema_version": 1,
        "generated_at_utc": generated_at,
        "runtime": {
            "python": report["environment"].get("python", sys.version),
            "python_version": platform.python_version(),
            "qiskit": report["environment"].get("qiskit", "unknown"),
            "qiskit_aer": aer,
            "qiskit_aer_status": "available" if aer else "absent",
        },
        "git": vcs,
        "commit": vcs.get("commit", "unknown"),
        "commit_confidence": vcs.get("confidence", "none"),
        "commit_verified": vcs.get("commit_verified", False),
        "generator": {
            "path": str(script_path),
            "sha256": hashlib.sha256(script_path.read_bytes()).hexdigest(),
            "command": report["command"],
        },
        "seeds": seeds,
        "scenarios": list(scenarios.values()),
        "scenario_digests": sorted(scenarios),
        "csv": {
            "path": str(csv_path) if csv_path is not None else "unknown",
            "sha256": csv_sha256 or "unknown",
            "row_count": csv_row_count,
        },
        "results": results,
        "result_ids": [result["result_id"] for result in results],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--csv", type=Path, help="write one row per case")
    parser.add_argument("--cases", nargs="*", metavar="NAME")
    parser.add_argument("--list-cases", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be at least 1")
    if args.warmups < 0:
        raise SystemExit("--warmups must be non-negative")
    case_by_name = {case.name: case for case in CASES}
    if args.list_cases:
        for case in CASES:
            print(case.name)
        return 0
    if args.cases:
        unknown = sorted(set(args.cases) - case_by_name.keys())
        if unknown:
            raise SystemExit(f"unknown benchmark cases: {', '.join(unknown)}")
        selected = tuple(case_by_name[name] for name in args.cases)
    else:
        selected = CASES

    report: dict[str, Any] = {
        "schema_version": 1,
        "workload_version": WORKLOAD_VERSION,
        "workload_fingerprint": _workload_fingerprint(selected),
        "repeats": args.repeats,
        "warmups": args.warmups,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "script": str(Path(__file__).resolve()),
        "command": [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        "environment": _environment(),
        "cases": [],
        "skipped": [],
    }
    for case in selected:
        if not case.available():
            report["skipped"].append(case.name)
            continue
        print(f"benchmark {case.name}", flush=True)
        for _ in range(args.warmups):
            _run_sample(case, track_memory=False)
        samples = [
            _run_sample(case, track_memory=True) for _ in range(args.repeats)
        ]
        for index, sample in enumerate(samples, start=1):
            sample["result_id"] = f"{case.name}-repeat-{index}"
        report["cases"].append(
            {
                "name": case.name,
                "size": case.size,
                "description": case.description,
                "samples": samples,
                "aggregate": _aggregate(samples),
            }
        )

    report["seeds"] = {
        case["name"]: sorted(
            {
                key: value
                for sample in case.get("samples", [])
                for key, value in sample.get("seeds", {}).items()
            }.items()
        )
        for case in report["cases"]
    }
    report["scenarios"] = {
        case["name"]: sorted(
            {
                sample.get("scenario", {}).get("digest", "")
                for sample in case.get("samples", [])
                if sample.get("scenario")
            }
        )
        for case in report["cases"]
    }

    # A requested JSON report is always accompanied by a CSV and an embedded
    # manifest.  This keeps persisted benchmark output self-describing even
    # when a caller only archives the JSON file.
    csv_path = args.csv
    if args.output is not None and csv_path is None:
        csv_path = args.output.with_suffix(".csv")
    if csv_path is not None:
        _write_csv(report, csv_path)
    csv_hash = (
        hashlib.sha256(csv_path.read_bytes()).hexdigest()
        if csv_path is not None and csv_path.exists()
        else None
    )
    report["manifest"] = _benchmark_manifest(
        report,
        csv_path=csv_path,
        csv_sha256=csv_hash,
        csv_row_count=len(report["cases"]),
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    elif csv_path is not None:
        # ``manifest_ref`` in each CSV row must resolve even when the caller
        # requested only ``--csv``.
        csv_manifest = csv_path.with_suffix(".json")
        csv_manifest.parent.mkdir(parents=True, exist_ok=True)
        csv_manifest.write_text(encoded, encoding="utf-8")
        print(f"Benchmark manifest: {csv_manifest}")
    else:
        print(encoded)
    if args.markdown:
        _write_markdown(report, args.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
