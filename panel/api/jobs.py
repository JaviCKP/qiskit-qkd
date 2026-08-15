"""Bounded, observable job execution with durable metadata.

The manager intentionally keeps worker controls and state transitions small and
explicit.  SQLite stores metadata; result payloads are atomically written by
``ArtifactStore`` and are loaded only when a caller asks for a result.
"""

from __future__ import annotations

import inspect
import logging
import math
import multiprocessing
import os
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from queue import Empty, SimpleQueue
from threading import Event, RLock, Thread
from typing import Any, Literal

from .artifact_store import (
    ArtifactCorruptError,
    ArtifactStore,
    ArtifactStoreError,
)
from .job_store import JobStore, JobStoreError, JobStoreVersionError

JobStatus = Literal[
    "queued",
    "running",
    "cancellation_requested",
    "cancelled",
    "timed_out",
    "done",
    "error",
    "interrupted",
    "expired",
]

ACTIVE_STATUSES = {"queued", "running", "cancellation_requested"}
TERMINAL_STATUSES = {"cancelled", "timed_out", "done", "error", "interrupted"}
_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled", "error", "interrupted"},
    "running": {
        "cancellation_requested",
        "cancelled",
        "timed_out",
        "done",
        "error",
        "interrupted",
    },
    "cancellation_requested": {
        "cancelled",
        "timed_out",
        "done",
        "error",
        "interrupted",
    },
    "cancelled": {"expired"},
    "timed_out": {"expired"},
    # A result is only complete after its artifact has been committed.  The
    # parent may therefore correct a provisional ``done`` to ``error`` when
    # that final durable write fails.
    "done": {"error", "expired"},
    "error": {"expired"},
    "interrupted": {"expired"},
    "expired": set(),
}

logger = logging.getLogger(__name__)


class JobCapacityError(RuntimeError):
    """Raised when accepting a job would exceed configured capacity."""


class JobManagerShutdownError(RuntimeError):
    """Raised when work is submitted after shutdown started."""


class CooperativeCancellation(Exception):
    """Private worker signal raised only at safe protocol checkpoints."""


@dataclass(slots=True)
class JobControl:
    """Pickle-safe worker controls backed by local or manager proxies."""

    cancellation_event: Any
    progress_queue: Any
    total: int
    completed: int = 0

    def checkpoint(self) -> None:
        if self.cancellation_event.is_set():
            raise CooperativeCancellation

    def report(self, completed: int) -> None:
        bounded = max(self.completed, min(int(completed), self.total))
        self.completed = bounded
        self.progress_queue.put(bounded)

    def advance(self, amount: int = 1) -> None:
        self.report(self.completed + amount)
        self.checkpoint()


@dataclass(frozen=True, slots=True)
class _WorkerOutcome:
    status: Literal["done", "cancelled"]
    result: Any = None


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: JobStatus
    progress: dict[str, int]
    created_at: float
    digest: str | None = None
    future: Future[Any] | None = None
    result: Any = None
    error: str | None = None
    error_code: str | None = None
    issues: list[dict[str, Any]] | None = None
    cancellation_event: Any = None
    progress_queue: Any = None
    timeout_s: float | None = None
    retention_s: float = 900.0
    started_at: float | None = None
    terminal_at: float | None = None
    expired_at: float | None = None
    timed_out: bool = False
    cancellation_requested_at: float | None = None
    created_at_utc: str = field(default_factory=lambda: _utc_now().isoformat())
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    expires_at_utc: str | None = None
    expired_at_utc: str | None = None
    updated_at_utc: str = field(default_factory=lambda: _utc_now().isoformat())
    artifact_path: str | None = None
    artifact_digest: str | None = None
    artifact_size_bytes: int = 0
    inline_result_bytes: int = 0
    result_summary: dict[str, Any] | None = None
    last_accessed_at: float | None = None
    last_accessed_at_utc: str | None = None
    cost: float = 1.0
    estimated_bytes: int = 0
    queue_depth: int = 0
    persist_callback: Callable[[JobRecord], None] | None = field(
        default=None, repr=False
    )
    artifact_loader: Callable[[JobRecord], Any] | None = field(default=None, repr=False)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def to_status(self) -> dict[str, Any]:
        self.refresh()
        with self._lock:
            elapsed_end = self.terminal_at or time.monotonic()
            payload: dict[str, Any] = {
                "job_id": self.job_id,
                "kind": self.kind,
                "status": self.status,
                "progress": dict(self.progress),
                "elapsed_s": round(max(0.0, elapsed_end - self.created_at), 3),
                "timestamps": {
                    "created_at": self.created_at_utc,
                    "started_at": self.started_at_utc,
                    "finished_at": self.finished_at_utc,
                    "expires_at": self.expires_at_utc,
                    "expired_at": self.expired_at_utc,
                    "updated_at": self.updated_at_utc,
                },
            }
            if self.timed_out:
                payload["timed_out"] = True
            if self.error is not None:
                payload["error"] = self.error
            if self.error_code is not None:
                payload["error_code"] = self.error_code
            if self.issues:
                payload["issues"] = [dict(issue) for issue in self.issues]
            if self.artifact_path is not None:
                payload["artifact"] = {
                    "digest": self.artifact_digest,
                    "size_bytes": self.artifact_size_bytes,
                }
            if self.result_summary is not None:
                payload["result_summary"] = dict(self.result_summary)
            # Small in-memory results retain the legacy shape.  Large or
            # restart-loaded results are represented by the artifact reference.
            if self.status == "done" and self.result is not None:
                payload["result"] = self.result
            return payload

    def get_result(self) -> Any:
        """Load a completed result lazily, tolerating artifact corruption."""
        with self._lock:
            self._touch_access()
            if self.result is not None:
                return self.result
            if self.status != "done" or self.artifact_loader is None:
                return None
        try:
            value = self.artifact_loader(self)
        except ArtifactCorruptError as exc:
            with self._lock:
                self.error = "The completed job result is unavailable."
                self.error_code = "ARTIFACT_CORRUPTED"
                self.issues = [{"code": "ARTIFACT_CORRUPTED", "msg": str(exc)}]
                self._persist()
            return None
        with self._lock:
            # Large artifacts are materialized only for the current response;
            # retaining them on the JobRecord would undo the bounded-memory
            # persistence design after the first download.
            if self.artifact_size_bytes <= self.inline_result_bytes:
                self.result = value
            return value

    def _touch_access(self) -> None:
        self.last_accessed_at = time.monotonic()
        self.last_accessed_at_utc = _utc_now().isoformat()
        self._persist()

    def refresh(self, *, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        with self._lock:
            previous_done = self.progress["done"]
            self._drain_progress()
            if self.progress["done"] != previous_done:
                self._persist()
            if self.status not in ACTIVE_STATUSES:
                return
            if self.future is None:
                return
            if self.future.cancelled():
                self._transition("cancelled", now=current, error_code="CANCELLED")
                return
            if self.future.done():
                self._consume_future(now=current)
                return
            if self.future.running() and self.status == "queued":
                self._transition("running", now=current)
            if (
                self.timeout_s is not None
                and self.started_at is not None
                and current - self.started_at >= self.timeout_s
                and self.status == "running"
            ):
                self.timed_out = True
                if self.cancellation_event is not None:
                    self.cancellation_event.set()
                self.cancellation_requested_at = current
                self._transition(
                    "cancellation_requested",
                    now=current,
                    error_code="TIMED_OUT",
                )

    def force_terminal(
        self, status: Literal["cancelled", "timed_out"], *, now: float
    ) -> None:
        with self._lock:
            if self.status not in ACTIVE_STATUSES:
                return
            if status == "timed_out":
                self.timed_out = True
                self._transition("timed_out", now=now, error_code="TIMED_OUT")
            else:
                self._transition("cancelled", now=now, error_code="CANCELLED")
            self.future = None
            self.cancellation_event = None
            self.progress_queue = None

    def expire(self, *, now: float) -> bool:
        with self._lock:
            if self.status not in TERMINAL_STATUSES or self.terminal_at is None:
                return False
            if now - self.terminal_at < self.retention_s:
                return False
            self._transition("expired", now=now)
            self.result = None
            self.error = None
            self.issues = None
            self.future = None
            self.cancellation_event = None
            self.progress_queue = None
            self._persist()
            return True

    def _consume_future(self, *, now: float) -> None:
        try:
            outcome = self.future.result() if self.future is not None else None
        except Exception as exc:  # pragma: no cover - worker boundary details vary
            if self.timed_out:
                self._transition("timed_out", now=now, error_code="TIMED_OUT")
            else:
                logger.exception("job worker failed", extra=_log_fields(self, "error"))
                self.error = _public_error(exc)
                self.issues = _exception_issues(exc)
                code = (
                    "WORKER_CRASHED" if _looks_like_worker_crash(exc) else "JOB_FAILED"
                )
                self._transition("error", now=now, error_code=code)
            return
        if isinstance(outcome, _WorkerOutcome):
            if outcome.status == "cancelled":
                self._transition(
                    "timed_out" if self.timed_out else "cancelled",
                    now=now,
                    error_code="TIMED_OUT" if self.timed_out else "CANCELLED",
                )
                return
            self.result = outcome.result
        else:
            self.result = outcome
        self.progress["done"] = self.progress["total"]
        # Once the timeout deadline was observed, timeout is the terminal
        # contract even if the worker returned while cancellation was being
        # requested.  Ordinary user cancellation keeps the historical
        # completion-wins race semantics.
        if self.timed_out:
            self._transition("timed_out", now=now, error_code="TIMED_OUT")
        else:
            self._transition("done", now=now)

    def _drain_progress(self) -> None:
        if self.progress_queue is None:
            return
        latest = self.progress["done"]
        while True:
            try:
                candidate = int(self.progress_queue.get_nowait())
            except Empty:
                break
            latest = max(latest, min(candidate, self.progress["total"]))
        self.progress["done"] = latest

    def _transition(
        self,
        new_status: JobStatus,
        *,
        now: float,
        error_code: str | None = None,
    ) -> None:
        if new_status == self.status:
            if error_code is not None:
                self.error_code = error_code
                self._persist()
            return
        allowed = _TRANSITIONS[self.status]
        if new_status not in allowed:
            raise RuntimeError(
                f"invalid job state transition {self.status!r} -> {new_status!r}",
            )
        wall_now = _utc_now()
        self.status = new_status
        self.updated_at_utc = wall_now.isoformat()
        if error_code is not None:
            self.error_code = error_code
        if new_status == "running" and self.started_at is None:
            self.started_at = now
            self.started_at_utc = wall_now.isoformat()
        if new_status in TERMINAL_STATUSES:
            self.terminal_at = now
            self.finished_at_utc = wall_now.isoformat()
            self.expires_at_utc = (
                wall_now + timedelta(seconds=self.retention_s)
            ).isoformat()
            if new_status != "done":
                self.result = None
            logger.info(
                "job terminal",
                extra=_log_fields(self, new_status),
            )
        if new_status == "expired":
            self.expired_at = now
            self.expired_at_utc = wall_now.isoformat()
        self._persist()

    def _persist(self) -> None:
        if self.persist_callback is not None:
            try:
                self.persist_callback(self)
            except JobStoreError:
                logger.exception(
                    "job metadata persistence failed",
                    extra=_log_fields(self, self.status),
                )


class JobManager:
    def __init__(
        self,
        *,
        use_processes: bool = True,
        max_workers: int | None = None,
        max_active_jobs: int = 32,
        max_records: int = 1_000,
        timeout_s: float | None = 600.0,
        timeout_grace_s: float = 2.0,
        cancellation_grace_s: float = 2.0,
        retention_s: float = 900.0,
        expired_tombstone_s: float = 60.0,
        max_queue_cost: float = math.inf,
        max_queue_bytes: int = 2**63 - 1,
        max_retention_bytes: int = 128 * 1024 * 1024,
        store_dir: str | os.PathLike[str] | None = None,
        artifact_dir: str | os.PathLike[str] | None = None,
        inline_result_bytes: int = 64 * 1024,
    ) -> None:
        workers = min(2, os.cpu_count() or 1) if max_workers is None else max_workers
        _require_positive_int("max_workers", workers)
        _require_positive_int("max_active_jobs", max_active_jobs)
        _require_positive_int("max_records", max_records)
        _require_positive_number("retention_s", retention_s)
        _require_positive_number("expired_tombstone_s", expired_tombstone_s)
        _require_non_negative_number("timeout_grace_s", timeout_grace_s)
        _require_non_negative_number("cancellation_grace_s", cancellation_grace_s)
        _require_non_negative_number("max_queue_cost", max_queue_cost)
        _require_non_negative_int("max_queue_bytes", max_queue_bytes)
        _require_non_negative_int("max_retention_bytes", max_retention_bytes)
        _require_non_negative_int("inline_result_bytes", inline_result_bytes)
        if timeout_s is not None:
            _require_positive_number("timeout_s", timeout_s)

        self.max_active_jobs = max_active_jobs
        self.max_records = max_records
        self.timeout_s = timeout_s
        self.timeout_grace_s = float(timeout_grace_s)
        self.cancellation_grace_s = float(cancellation_grace_s)
        self.retention_s = retention_s
        self.expired_tombstone_s = expired_tombstone_s
        self.max_queue_cost = float(max_queue_cost)
        self.max_queue_bytes = int(max_queue_bytes)
        self.max_retention_bytes = int(max_retention_bytes)
        self.inline_result_bytes = inline_result_bytes
        self._records: dict[str, JobRecord] = {}
        self._lock = RLock()
        self._shutdown = False
        self._mp_context = multiprocessing.get_context("spawn")
        self._shared_manager: Any = None
        self._executor: Any = None
        self._sweep_executor: Any = None
        self._executor_owned = True
        self._use_processes = bool(use_processes)
        self._workers = workers
        self._monitor_stop = Event()
        self._monitor_thread: Thread | None = None
        self._store: JobStore | None = None
        self._artifacts: ArtifactStore | None = None
        self.degraded_reasons: list[str] = []
        if store_dir is not None:
            root = os.fspath(store_dir)
            root_path = os.path.abspath(root)
            self._store_path = os.path.join(root_path, "jobs.sqlite3")
            artifact_root = (
                os.fspath(artifact_dir)
                if artifact_dir is not None
                else os.path.join(root_path, "artifacts")
            )
            try:
                self._store = JobStore(self._store_path)
                self._store.mark_interrupted(ACTIVE_STATUSES)
            except JobStoreVersionError:
                raise
            except JobStoreError as exc:
                self.degraded_reasons.append(str(exc))
                self._store = None
            try:
                self._artifacts = ArtifactStore(artifact_root)
                if not self._artifacts.available and self._artifacts.degraded_reason:
                    self.degraded_reasons.append(self._artifacts.degraded_reason)
            except (OSError, ArtifactStoreError) as exc:
                self.degraded_reasons.append(f"artifact store unavailable: {exc}")
                self._artifacts = None
        if self._store is not None and self._store.available:
            self._load_persisted()
        self._create_executor()

    def _create_executor(self) -> None:
        if not self._use_processes:
            # The explicit no-process mode is a deterministic local fallback:
            # submit executes inline (see ``submit``).  This avoids pretending
            # that a Python thread can be terminated safely after a timeout.
            self._executor = None
            self._sweep_executor = None
            return
        # Keep one worker partition for sweeps and one for short runs.  A
        # maximal sweep therefore cannot occupy the only worker ahead of a
        # cheap run.  Each pool is process-isolated and can be recreated after
        # a non-cooperating worker exceeds its grace period.
        main_workers = max(1, self._workers - 1) if self._workers > 1 else 1
        self._executor = ProcessPoolExecutor(
            max_workers=main_workers,
            mp_context=self._mp_context,
        )
        self._sweep_executor = ProcessPoolExecutor(
            max_workers=1,
            mp_context=self._mp_context,
        )
        self._executor_owned = True

    def _load_persisted(self) -> None:
        assert self._store is not None
        try:
            persisted = self._store.load_all()
        except JobStoreError as exc:
            self.degraded_reasons.append(str(exc))
            return
        if self._store.corrupt_rows_skipped:
            self.degraded_reasons.append(
                "skipped "
                f"{self._store.corrupt_rows_skipped} corrupt job metadata row(s)"
            )
        for item in persisted:
            status = item.status
            if status not in _TRANSITIONS:
                status = "error"
            artifact_path = item.artifact_path
            artifact_digest = item.artifact_digest
            artifact_size_bytes = item.artifact_size_bytes
            recovered_artifact = False
            if (
                status == "done"
                and artifact_path is None
                and self._artifacts is not None
            ):
                try:
                    reference = self._artifacts.reference_existing(item.job_id)
                except ArtifactStoreError:
                    pass
                else:
                    artifact_path = reference.path
                    artifact_digest = reference.digest
                    artifact_size_bytes = reference.size_bytes
                    recovered_artifact = True
            terminal_at = _wall_to_mono(item.finished_at_utc or item.updated_at_utc)
            record = JobRecord(
                job_id=item.job_id,
                kind=item.kind,
                status=status,  # type: ignore[arg-type]
                progress={"done": item.progress_done, "total": item.progress_total},
                created_at=_wall_to_mono(item.created_at_utc),
                digest=item.digest,
                timeout_s=self.timeout_s,
                retention_s=self.retention_s,
                started_at=_wall_to_mono(item.started_at_utc)
                if item.started_at_utc
                else None,
                terminal_at=terminal_at if status in TERMINAL_STATUSES else None,
                expired_at=_wall_to_mono(item.expired_at_utc)
                if status == "expired" and item.expired_at_utc
                else None,
                timed_out=item.timed_out,
                created_at_utc=item.created_at_utc,
                started_at_utc=item.started_at_utc,
                finished_at_utc=item.finished_at_utc,
                expires_at_utc=item.expires_at_utc,
                expired_at_utc=item.expired_at_utc,
                updated_at_utc=item.updated_at_utc,
                error=item.error,
                error_code=item.error_code,
                issues=item.issues,
                artifact_path=artifact_path,
                artifact_digest=artifact_digest,
                artifact_size_bytes=artifact_size_bytes,
                inline_result_bytes=self.inline_result_bytes,
                result_summary=item.result_summary,
                last_accessed_at=(
                    _wall_to_mono(item.last_accessed_at_utc)
                    if item.last_accessed_at_utc
                    else terminal_at
                ),
                last_accessed_at_utc=item.last_accessed_at_utc,
                cost=item.cost,
                estimated_bytes=item.estimated_bytes,
                persist_callback=self._persist_record,
                artifact_loader=self._load_artifact,
            )
            self._records[item.job_id] = record
            if recovered_artifact:
                try:
                    self._store.upsert(record)
                except JobStoreError as exc:
                    self.degraded_reasons.append(str(exc))

    def submit(
        self,
        kind: str,
        fn: Callable[..., Any],
        *args: Any,
        total: int = 1,
        cost: float = 1.0,
        estimated_bytes: int = 0,
        digest: str | None = None,
    ) -> JobRecord:
        _require_positive_int("total", total)
        _require_positive_number("cost", cost)
        _require_non_negative_int("estimated_bytes", estimated_bytes)
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError(f"kind must be a non-empty string, got {kind!r}")
        with self._lock:
            if self._shutdown:
                raise JobManagerShutdownError(
                    "JobManager is shut down and cannot accept new work."
                )
            self._cleanup_locked(now=time.monotonic())
            active_records = [
                record
                for record in self._records.values()
                if record.status in ACTIVE_STATUSES
            ]
            if len(active_records) >= self.max_active_jobs:
                raise JobCapacityError(
                    "JobManager active-job limit reached; retry after a job finishes."
                )
            queued_cost = sum(record.cost for record in active_records)
            queued_bytes = sum(record.estimated_bytes for record in active_records)
            if queued_cost + float(cost) > self.max_queue_cost:
                raise JobCapacityError(
                    f"JobManager cost budget exceeded: requested={cost!r}, available="
                    f"{max(0.0, self.max_queue_cost - queued_cost)!r}."
                )
            if queued_bytes + estimated_bytes > self.max_queue_bytes:
                raise JobCapacityError(
                    "JobManager byte budget exceeded: "
                    f"requested={estimated_bytes}, available="
                    f"{max(0, self.max_queue_bytes - queued_bytes)}."
                )
            self._make_record_space()
            job_id = f"{kind[0]}_{uuid.uuid4().hex[:12]}"
            cancellation_event, progress_queue = self._new_worker_channels()
            control = JobControl(cancellation_event, progress_queue, total)
            record = JobRecord(
                job_id=job_id,
                kind=kind,
                digest=digest,
                status="queued",
                progress={"done": 0, "total": total},
                created_at=time.monotonic(),
                cancellation_event=cancellation_event,
                progress_queue=progress_queue,
                timeout_s=self.timeout_s,
                retention_s=self.retention_s,
                inline_result_bytes=self.inline_result_bytes,
                cost=float(cost),
                estimated_bytes=estimated_bytes,
                queue_depth=len(active_records),
                persist_callback=self._persist_record,
                artifact_loader=self._load_artifact,
            )
            self._records[job_id] = record
            self._persist_record(record)
            executor = (
                self._sweep_executor
                if kind == "sweep" and self._sweep_executor is not None
                else self._executor
            )
            if executor is not None:
                self._start_monitor_locked()
                try:
                    record.future = executor.submit(
                        _execute_controlled_job, fn, args, control
                    )
                    logger.info("job queued", extra=_log_fields(record, "queued"))
                except Exception as exc:
                    logger.exception(
                        "job submit failed", extra=_log_fields(record, "error")
                    )
                    with record._lock:
                        record.error = "The job could not be submitted."
                        record.error_code = "SUBMIT_FAILED"
                        record.issues = _exception_issues(exc)
                        record._transition(
                            "error", now=time.monotonic(), error_code="SUBMIT_FAILED"
                        )
        if executor is None:
            # Inline mode is intentionally only a local/test fallback.  It is
            # cooperative, so cancellation/timeout cannot claim to terminate
            # arbitrary user code running on this thread.
            with record._lock:
                record._transition("running", now=time.monotonic())
            try:
                outcome = _execute_controlled_job(fn, args, control)
            except Exception as exc:  # pragma: no cover - defensive boundary
                logger.exception(
                    "inline job failed", extra=_log_fields(record, "error")
                )
                with record._lock:
                    record.error = _public_error(exc)
                    record.error_code = "JOB_FAILED"
                    record.issues = _exception_issues(exc)
                    record._transition(
                        "error", now=time.monotonic(), error_code="JOB_FAILED"
                    )
            else:
                _apply_worker_outcome(record, outcome)
        else:
            record.refresh()
        return record

    def get(self, job_id: str, *, kind: str | None = None) -> JobRecord | None:
        with self._lock:
            self._cleanup_locked(now=time.monotonic())
            record = self._records.get(job_id)
            if record is not None and kind is not None and record.kind != kind:
                return None
            if record is not None:
                record.refresh()
            return record

    def list(self, *, kind: str | None = None) -> list[JobRecord]:
        with self._lock:
            self._cleanup_locked(now=time.monotonic())
            records = [
                record
                for record in self._records.values()
                if kind is None or record.kind == kind
            ]
            for record in records:
                record.refresh()
            return sorted(records, key=lambda item: item.created_at, reverse=True)

    def cancel(self, job_id: str, *, kind: str | None = None) -> bool:
        with self._lock:
            self._cleanup_locked(now=time.monotonic())
            record = self._records.get(job_id)
            if record is None or (kind is not None and record.kind != kind):
                return False
            record.refresh()
            with record._lock:
                if record.status not in ACTIVE_STATUSES:
                    return False
                if record.future is not None and record.future.cancel():
                    record._transition(
                        "cancelled", now=time.monotonic(), error_code="CANCELLED"
                    )
                    return True
                record.refresh()
                if record.status == "running" and record.cancellation_event is not None:
                    record.cancellation_event.set()
                    record.cancellation_requested_at = time.monotonic()
                    record._transition(
                        "cancellation_requested",
                        now=time.monotonic(),
                        error_code="CANCELLED",
                    )
                return False

    def cleanup(self, *, now: float | None = None) -> dict[str, int]:
        with self._lock:
            return self._cleanup_locked(now=time.monotonic() if now is None else now)

    def readiness(self) -> dict[str, Any]:
        with self._lock:
            store_ok, store_reason = (
                self._store.check() if self._store is not None else (True, None)
            )
            artifact_ok, artifact_reason = (
                self._artifacts.check() if self._artifacts is not None else (True, None)
            )
            active = sum(
                record.status in ACTIVE_STATUSES for record in self._records.values()
            )
            reasons = list(self.degraded_reasons)
            reasons.extend(
                reason for reason in (store_reason, artifact_reason) if reason
            )
            worker_ok = self._executor is not None or not self._use_processes
            if not worker_ok:
                reasons.append("worker executor unavailable")
            if active >= self.max_active_jobs:
                reasons.append("active-job capacity exhausted")
            return {
                "ready": not reasons
                and not self._shutdown
                and store_ok
                and artifact_ok
                and worker_ok,
                "reasons": sorted(set(reasons)),
                "queue": {
                    "active": active,
                    "capacity": self.max_active_jobs,
                    "cost": sum(
                        r.cost
                        for r in self._records.values()
                        if r.status in ACTIVE_STATUSES
                    ),
                    "bytes": sum(
                        r.estimated_bytes
                        for r in self._records.values()
                        if r.status in ACTIVE_STATUSES
                    ),
                },
            }

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            records = list(self._records.values())
            executors = [
                executor
                for executor in (self._executor, self._sweep_executor)
                if executor is not None
            ]
            shared_manager = self._shared_manager
            monitor_thread = self._monitor_thread
            self._monitor_stop.set()
        for record in records:
            with record._lock:
                record.refresh()
                if record.status not in ACTIVE_STATUSES:
                    continue
                if record.future is not None and record.future.cancel():
                    record._transition(
                        "cancelled", now=time.monotonic(), error_code="CANCELLED"
                    )
                elif record.cancellation_event is not None:
                    record.cancellation_event.set()
                    record.cancellation_requested_at = time.monotonic()
                    if record.status == "running":
                        record._transition(
                            "cancellation_requested",
                            now=time.monotonic(),
                            error_code="CANCELLED",
                        )
                # Shutdown is an explicit lifecycle boundary.  Mark any
                # non-cooperative work terminal before terminating only the
                # manager-owned process below; no worker is left orphaned.
                if record.status in ACTIVE_STATUSES:
                    record.force_terminal("cancelled", now=time.monotonic())
        for executor in executors:
            if self._use_processes:
                for process in list(getattr(executor, "_processes", {}).values()):
                    try:
                        if process.is_alive():
                            process.terminate()
                    except Exception:
                        logger.exception("worker termination during shutdown failed")
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:  # custom executor in tests
                executor.shutdown(wait=False)
        if monitor_thread is not None:
            monitor_thread.join(timeout=max(0.1, self.cancellation_grace_s + 0.25))
        if shared_manager is not None:
            shutdown_thread = Thread(target=shared_manager.shutdown, daemon=True)
            shutdown_thread.start()
            shutdown_thread.join(timeout=1.0)
        if self._store is not None:
            self._store.close()

    def _new_worker_channels(self) -> tuple[Any, Any]:
        if not self._use_processes:
            return Event(), SimpleQueue()
        if self._shared_manager is None:
            self._shared_manager = self._mp_context.Manager()
        return self._shared_manager.Event(), self._shared_manager.Queue()

    def _start_monitor_locked(self) -> None:
        if self._monitor_thread is not None:
            return
        candidates = [1.0, self.retention_s / 10.0, self.expired_tombstone_s / 10.0]
        if self.timeout_s is not None:
            candidates.append(max(0.01, self.timeout_s / 10.0))
        candidates.append(max(0.01, self.timeout_grace_s / 2.0))
        candidates.append(max(0.01, self.cancellation_grace_s / 2.0))
        interval_s = max(0.02, min(candidates))
        self._monitor_thread = Thread(
            target=self._monitor,
            args=(interval_s,),
            name="qkd-job-monitor",
            daemon=True,
        )
        self._monitor_thread.start()

    def _monitor(self, interval_s: float) -> None:
        while not self._monitor_stop.wait(interval_s):
            try:
                self.cleanup()
            except Exception:  # pragma: no cover - defensive monitor boundary
                logger.exception("job monitor cleanup failed")

    def _cleanup_locked(self, *, now: float) -> dict[str, int]:
        expired = 0
        removed_ids: list[str] = []
        aborted_kinds: set[str] = set()
        for job_id, record in list(self._records.items()):
            previous = record.status
            record.refresh(now=now)
            if (
                record.status == "cancellation_requested"
                and record.cancellation_requested_at is not None
            ):
                grace = (
                    self.timeout_grace_s
                    if record.timed_out
                    else self.cancellation_grace_s
                )
                if now - record.cancellation_requested_at >= grace:
                    record.force_terminal(
                        "timed_out" if record.timed_out else "cancelled", now=now
                    )
                    aborted_kinds.add(record.kind)
            if record.expire(now=now):
                expired += 1
                if self._artifacts is not None and record.artifact_path is not None:
                    try:
                        self._artifacts.delete(record.job_id)
                    except ArtifactStoreError:
                        logger.exception(
                            "artifact retention cleanup failed",
                            extra=_log_fields(record, "expired"),
                        )
            if (
                record.status == "expired"
                and record.expired_at is not None
                and now - record.expired_at >= self.expired_tombstone_s
            ):
                removed_ids.append(job_id)
            if previous != record.status:
                record._persist()
        if aborted_kinds:
            self._abort_and_recreate_executor_locked(aborted_kinds)
        for job_id in removed_ids:
            record = self._records.pop(job_id, None)
            if record is not None and self._store is not None:
                try:
                    self._store.delete_metadata(job_id)
                except JobStoreError:
                    logger.exception(
                        "job metadata tombstone removal failed",
                        extra={"job_id": job_id},
                    )
        self._enforce_retention_locked()
        return {"expired": expired, "removed": len(removed_ids)}

    def _abort_and_recreate_executor_locked(self, kinds: set[str]) -> None:
        if not self._use_processes or not self._executor_owned:
            return
        pool_specs: list[tuple[str, Any]] = []
        if any(kind != "sweep" for kind in kinds) and self._executor is not None:
            pool_specs.append(("main", self._executor))
        if "sweep" in kinds and self._sweep_executor is not None:
            pool_specs.append(("sweep", self._sweep_executor))
        # Resolve active records before killing a pool.  Healthy work in the
        # other partition is intentionally left untouched.
        main_needed = any(kind != "sweep" for kind in kinds)
        sweep_needed = "sweep" in kinds
        for record in self._records.values():
            if record.status not in ACTIVE_STATUSES:
                continue
            in_target_pool = sweep_needed if record.kind == "sweep" else main_needed
            if not in_target_pool:
                continue
            if record.status not in {"timed_out", "cancelled"}:
                with record._lock:
                    record.error = (
                        "The worker process was terminated after exceeding its "
                        "grace period."
                    )
                    record.error_code = "WORKER_CRASHED"
                    record._transition(
                        "error", now=time.monotonic(), error_code="WORKER_CRASHED"
                    )
                    record.future = None
                    record.cancellation_event = None
                    record.progress_queue = None
        for pool_name, executor in pool_specs:
            try:
                # ProcessPoolExecutor exposes its owned worker handles.  Restrict
                # termination to this executor and bound the join; no global kill.
                for process in list(getattr(executor, "_processes", {}).values()):
                    if process.is_alive():
                        process.terminate()
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                logger.exception(
                    "worker executor abort failed", extra={"pool": pool_name}
                )
            if pool_name == "sweep":
                self._sweep_executor = None
            else:
                self._executor = None
        if not self._shutdown:
            for pool_name, _executor in pool_specs:
                try:
                    if pool_name == "sweep":
                        self._sweep_executor = ProcessPoolExecutor(
                            max_workers=1,
                            mp_context=self._mp_context,
                        )
                    else:
                        main_workers = (
                            max(1, self._workers - 1) if self._workers > 1 else 1
                        )
                        self._executor = ProcessPoolExecutor(
                            max_workers=main_workers,
                            mp_context=self._mp_context,
                        )
                except Exception as exc:
                    self.degraded_reasons.append(
                        f"{pool_name} worker recreation failed: {exc}"
                    )

    def _make_record_space(self) -> None:
        if len(self._records) < self.max_records:
            return
        removable = sorted(
            (
                record
                for record in self._records.values()
                if record.status not in ACTIVE_STATUSES
            ),
            key=lambda record: record.terminal_at or record.created_at,
        )
        while len(self._records) >= self.max_records and removable:
            record = removable.pop(0)
            self._remove_record_locked(record)
        if len(self._records) >= self.max_records:
            raise JobCapacityError(
                "JobManager record limit reached while all records are active."
            )

    def _enforce_retention_locked(self) -> None:
        if self._artifacts is None:
            return
        total = sum(
            record.artifact_size_bytes
            for record in self._records.values()
            if record.status in TERMINAL_STATUSES
        )
        if total <= self.max_retention_bytes:
            return
        candidates = sorted(
            (
                record
                for record in self._records.values()
                if record.status in TERMINAL_STATUSES
            ),
            key=lambda record: (
                record.last_accessed_at
                or record.terminal_at
                or record.created_at
            ),
        )
        for record in candidates:
            if total <= self.max_retention_bytes:
                break
            if self._remove_record_locked(record):
                total -= record.artifact_size_bytes

    def _remove_record_locked(self, record: JobRecord) -> bool:
        if record.status in ACTIVE_STATUSES:
            return False
        if self._artifacts is not None and record.artifact_path is not None:
            try:
                self._artifacts.delete(record.job_id)
            except ArtifactStoreError:
                logger.exception(
                    "artifact removal failed", extra=_log_fields(record, "expired")
                )
                return False
        if self._store is not None:
            try:
                self._store.delete_metadata(record.job_id)
            except JobStoreError:
                logger.exception(
                    "job metadata removal failed", extra={"job_id": record.job_id}
                )
                return False
        self._records.pop(record.job_id, None)
        return True

    def _persist_record(self, record: JobRecord) -> None:
        store = self._store
        if store is None or not store.available:
            return
        needs_artifact = (
            record.status == "done"
            and record.result is not None
            and record.artifact_path is None
            and self._artifacts is not None
        )
        if record.status == "done" and isinstance(record.result, dict):
            summary = record.result.get("result_summary")
            if isinstance(summary, dict):
                record.result_summary = dict(summary)
        if needs_artifact:
            # Phase one makes the terminal job intent durable before the file
            # write.  If the process stops after the write but before phase two,
            # startup recovers the stable <job_id>.json artifact by its row.
            try:
                store.upsert(record)
            except JobStoreError:
                if str(store.degraded_reason) not in self.degraded_reasons:
                    self.degraded_reasons.append(str(store.degraded_reason))
                return
            if not self._finalize_artifact(record):
                return
        try:
            store.upsert(record)
        except JobStoreError:
            if str(store.degraded_reason) not in self.degraded_reasons:
                self.degraded_reasons.append(str(store.degraded_reason))
            return
        if needs_artifact and record.artifact_size_bytes > self.inline_result_bytes:
            record.result = None

    def _load_artifact(self, record: JobRecord) -> Any:
        if self._artifacts is None:
            raise ArtifactCorruptError(
                f"artifact store unavailable for job {record.job_id!r}"
            )
        return self._artifacts.read_json(record.job_id, digest=record.artifact_digest)

    def _finalize_artifact(self, record: JobRecord) -> bool:
        if record.status != "done" or self._artifacts is None or record.result is None:
            return False
        try:
            ref = self._artifacts.write_json(record.job_id, record.result)
        except ArtifactStoreError as exc:
            record.error = "The completed job result could not be stored."
            record.error_code = "ARTIFACT_WRITE_FAILED"
            record.issues = [{"code": "ARTIFACT_WRITE_FAILED", "msg": str(exc)}]
            record._transition(
                "error", now=time.monotonic(), error_code="ARTIFACT_WRITE_FAILED"
            )
            return False
        record.artifact_path = ref.path
        record.artifact_digest = ref.digest
        record.artifact_size_bytes = ref.size_bytes
        return True


def _execute_controlled_job(
    fn: Callable[..., Any], args: tuple[Any, ...], control: JobControl
) -> _WorkerOutcome:
    try:
        control.checkpoint()
        signature = inspect.signature(fn)
        accepts_control = "job_control" in signature.parameters or any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        result = fn(*args, job_control=control) if accepts_control else fn(*args)
        control.checkpoint()
        control.report(control.total)
        return _WorkerOutcome("done", result)
    except CooperativeCancellation:
        return _WorkerOutcome("cancelled")


def _apply_worker_outcome(record: JobRecord, outcome: _WorkerOutcome) -> None:
    with record._lock:
        record._drain_progress()
        if outcome.status == "cancelled":
            record._transition(
                "cancelled", now=time.monotonic(), error_code="CANCELLED"
            )
            return
        record.result = outcome.result
        record.progress["done"] = record.progress["total"]
        record._transition("done", now=time.monotonic())


def _public_error(_exc: Exception) -> str:
    return "The job failed; consult server logs for details."


def _exception_issues(exc: Exception) -> list[dict[str, Any]] | None:
    errors = getattr(exc, "errors", None)
    if isinstance(errors, list) and all(isinstance(issue, dict) for issue in errors):
        return [dict(issue) for issue in errors]
    issues = getattr(exc, "issues", None)
    if not isinstance(issues, tuple | list):
        return None
    payload: list[dict[str, Any]] = []
    for issue in issues:
        to_dict = getattr(issue, "to_dict", None)
        if callable(to_dict):
            serialized = to_dict()
            if isinstance(serialized, dict):
                payload.append(dict(serialized))
    return payload or None


def _looks_like_worker_crash(exc: Exception) -> bool:
    return (
        type(exc).__name__ in {"BrokenProcessPool", "BrokenExecutor"}
        or "process pool" in str(exc).lower()
    )


def _log_fields(record: JobRecord, status: str) -> dict[str, Any]:
    duration_ms = None
    if record.started_at is not None:
        duration_ms = round(
            max(0.0, (record.terminal_at or time.monotonic()) - record.started_at)
            * 1000.0,
            3,
        )
    return {
        "job_id": record.job_id,
        "kind": record.kind,
        "digest": record.digest,
        "duration_ms": duration_ms,
        "queue_depth": record.queue_depth,
        "cost": record.cost,
        "estimated_bytes": record.estimated_bytes,
        "status": status,
        "error_code": record.error_code,
    }


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _wall_to_mono(value: str | None) -> float:
    if value is None:
        return time.monotonic()
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return time.monotonic() - max(0.0, (_utc_now() - parsed).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return time.monotonic()


def _require_positive_int(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")


def _require_non_negative_int(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")


def _require_positive_number(name: str, value: Any) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
        or value <= 0.0
    ):
        raise ValueError(f"{name} must be a positive number, got {value!r}")


def _require_non_negative_number(name: str, value: Any) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or (not math.isfinite(float(value)) and value != math.inf)
        or value < 0.0
    ):
        raise ValueError(f"{name} must be a non-negative number, got {value!r}")
