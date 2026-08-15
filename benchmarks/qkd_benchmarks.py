"""Bounded, reproducible benchmarks for the QKD engine and panel workloads."""

from __future__ import annotations

import argparse
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", type=Path)
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
        report["cases"].append(
            {
                "name": case.name,
                "size": case.size,
                "description": case.description,
                "samples": samples,
                "aggregate": _aggregate(samples),
            }
        )

    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded)
    if args.markdown:
        _write_markdown(report, args.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
