"""SQLite metadata persistence for panel jobs.

Only bounded metadata and an artifact reference are persisted here.  Result
payloads live in :mod:`panel.api.artifact_store`, which keeps SQLite records
small and makes large result retention independently enforceable.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

JOB_DB_SCHEMA_VERSION = 2
logger = logging.getLogger(__name__)


class JobStoreError(RuntimeError):
    """Base class for metadata persistence errors."""


class JobStoreVersionError(JobStoreError):
    """The on-disk schema is newer than this reader understands."""


@dataclass(frozen=True, slots=True)
class PersistedJob:
    job_id: str
    kind: str
    digest: str | None
    status: str
    progress_done: int
    progress_total: int
    created_at_utc: str
    started_at_utc: str | None
    finished_at_utc: str | None
    expires_at_utc: str | None
    expired_at_utc: str | None
    updated_at_utc: str
    timed_out: bool
    error: str | None
    error_code: str | None
    issues: list[dict[str, Any]] | None
    artifact_path: str | None
    artifact_digest: str | None
    artifact_size_bytes: int
    result_summary: dict[str, Any] | None
    last_accessed_at_utc: str | None
    cost: float
    estimated_bytes: int


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class JobStore:
    """Thread-safe SQLite metadata store with idempotent migrations."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.connection: sqlite3.Connection | None = None
        self.available = False
        self.degraded_reason: str | None = None
        self.corrupt_rows_skipped = 0
        try:
            self.connection = sqlite3.connect(
                self.path,
                timeout=5.0,
                isolation_level=None,
                check_same_thread=False,
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
            self._migrate()
            self.available = True
        except JobStoreVersionError:
            self.close()
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            self.degraded_reason = f"job metadata database unavailable: {exc}"
            if self.connection is not None:
                try:
                    self.connection.close()
                except sqlite3.Error:
                    pass
                self.connection = None

    def _require_connection(self) -> sqlite3.Connection:
        if self.connection is None or not self.available:
            raise JobStoreError(
                self.degraded_reason or "job metadata database unavailable"
            )
        return self.connection

    def _migrate(self) -> None:
        conn = self.connection
        if conn is None:
            raise JobStoreError("job metadata database connection missing")
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        if current > JOB_DB_SCHEMA_VERSION:
            raise JobStoreVersionError(
                f"job metadata schema version {current} is newer than supported "
                f"version {JOB_DB_SCHEMA_VERSION}; upgrade qiskit-qkd before starting"
            )
        try:
            if current < 1:
                conn.executescript(
                    """
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        kind TEXT NOT NULL,
                        digest TEXT,
                        status TEXT NOT NULL,
                        progress_done INTEGER NOT NULL,
                        progress_total INTEGER NOT NULL,
                        created_at_utc TEXT NOT NULL,
                        started_at_utc TEXT,
                        finished_at_utc TEXT,
                        expires_at_utc TEXT,
                        expired_at_utc TEXT,
                        updated_at_utc TEXT NOT NULL,
                        timed_out INTEGER NOT NULL DEFAULT 0,
                        error TEXT,
                        error_code TEXT,
                        issues_json TEXT,
                        artifact_path TEXT,
                        artifact_digest TEXT,
                        artifact_size_bytes INTEGER NOT NULL DEFAULT 0,
                        cost REAL NOT NULL DEFAULT 1.0,
                        estimated_bytes INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_jobs_status_updated
                        ON jobs(status, updated_at_utc);
                    PRAGMA user_version = 1;
                    COMMIT;
                    """
                )
                current = 1
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "digest" not in columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN digest TEXT")
            if current < 2:
                conn.execute("BEGIN IMMEDIATE")
                if "result_summary_json" not in columns:
                    conn.execute(
                        "ALTER TABLE jobs ADD COLUMN result_summary_json TEXT"
                    )
                if "last_accessed_at_utc" not in columns:
                    conn.execute(
                        "ALTER TABLE jobs ADD COLUMN last_accessed_at_utc TEXT"
                    )
                conn.execute("PRAGMA user_version = 2")
                conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise

    def close(self) -> None:
        with self._lock:
            if self.connection is not None:
                try:
                    self.connection.close()
                finally:
                    self.connection = None
                    self.available = False

    def create(self, record: Any) -> None:
        self.upsert(record)

    def upsert(self, record: Any) -> None:
        conn = self._require_connection()
        issues_json = (
            json.dumps(record.issues, ensure_ascii=False, sort_keys=True)
            if record.issues is not None
            else None
        )
        result_summary_json = (
            json.dumps(
                record.result_summary,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            if record.result_summary is not None
            else None
        )
        with self._lock:
            try:
                conn.execute(
                    """
                    INSERT INTO jobs (
                        job_id, kind, digest, status, progress_done, progress_total,
                        created_at_utc, started_at_utc, finished_at_utc,
                        expires_at_utc, expired_at_utc, updated_at_utc,
                        timed_out, error, error_code, issues_json,
                        artifact_path, artifact_digest, artifact_size_bytes,
                        cost, estimated_bytes, result_summary_json,
                        last_accessed_at_utc
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?
                    )
                    ON CONFLICT(job_id) DO UPDATE SET
                        kind=excluded.kind,
                        digest=excluded.digest,
                        status=excluded.status,
                        progress_done=excluded.progress_done,
                        progress_total=excluded.progress_total,
                        created_at_utc=excluded.created_at_utc,
                        started_at_utc=excluded.started_at_utc,
                        finished_at_utc=excluded.finished_at_utc,
                        expires_at_utc=excluded.expires_at_utc,
                        expired_at_utc=excluded.expired_at_utc,
                        updated_at_utc=excluded.updated_at_utc,
                        timed_out=excluded.timed_out,
                        error=excluded.error,
                        error_code=excluded.error_code,
                        issues_json=excluded.issues_json,
                        artifact_path=excluded.artifact_path,
                        artifact_digest=excluded.artifact_digest,
                        artifact_size_bytes=excluded.artifact_size_bytes,
                        cost=excluded.cost,
                        estimated_bytes=excluded.estimated_bytes,
                        result_summary_json=excluded.result_summary_json,
                        last_accessed_at_utc=excluded.last_accessed_at_utc
                    """,
                    (
                        record.job_id,
                        record.kind,
                        getattr(record, "digest", None),
                        record.status,
                        int(record.progress.get("done", 0)),
                        int(record.progress.get("total", 0)),
                        record.created_at_utc,
                        record.started_at_utc,
                        record.finished_at_utc,
                        record.expires_at_utc,
                        record.expired_at_utc,
                        record.updated_at_utc,
                        int(bool(record.timed_out)),
                        record.error,
                        getattr(record, "error_code", None),
                        issues_json,
                        getattr(record, "artifact_path", None),
                        getattr(record, "artifact_digest", None),
                        int(getattr(record, "artifact_size_bytes", 0)),
                        float(getattr(record, "cost", 1.0)),
                        int(getattr(record, "estimated_bytes", 0)),
                        result_summary_json,
                        getattr(record, "last_accessed_at_utc", None),
                    ),
                )
            except sqlite3.DatabaseError as exc:
                self.available = False
                self.degraded_reason = f"job metadata write failed: {exc}"
                raise JobStoreError(self.degraded_reason) from exc

    def load_all(self) -> list[PersistedJob]:
        conn = self._require_connection()
        self.corrupt_rows_skipped = 0
        try:
            with self._lock:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at_utc, job_id"
                ).fetchall()
        except sqlite3.DatabaseError as exc:
            self.available = False
            self.degraded_reason = f"job metadata read failed: {exc}"
            raise JobStoreError(self.degraded_reason) from exc
        result: list[PersistedJob] = []
        for row in rows:
            try:
                summary_raw = (
                    json.loads(row["result_summary_json"])
                    if row["result_summary_json"]
                    else None
                )
                result_summary = (
                    summary_raw if isinstance(summary_raw, dict) else None
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                result_summary = None
            try:
                issues = _decode_issues(row["issues_json"])
                persisted = PersistedJob(
                    job_id=str(row["job_id"]),
                    kind=str(row["kind"]),
                    digest=row["digest"] if "digest" in row.keys() else None,
                    status=str(row["status"]),
                    progress_done=int(row["progress_done"]),
                    progress_total=int(row["progress_total"]),
                    created_at_utc=str(row["created_at_utc"]),
                    started_at_utc=row["started_at_utc"],
                    finished_at_utc=row["finished_at_utc"],
                    expires_at_utc=row["expires_at_utc"],
                    expired_at_utc=row["expired_at_utc"],
                    updated_at_utc=str(row["updated_at_utc"]),
                    timed_out=bool(row["timed_out"]),
                    error=row["error"],
                    error_code=row["error_code"],
                    issues=issues,
                    artifact_path=row["artifact_path"],
                    artifact_digest=row["artifact_digest"],
                    artifact_size_bytes=int(row["artifact_size_bytes"] or 0),
                    cost=float(row["cost"] or 1.0),
                    estimated_bytes=int(row["estimated_bytes"] or 0),
                    result_summary=result_summary,
                    last_accessed_at_utc=row["last_accessed_at_utc"],
                )
                _validate_persisted_job(persisted)
            except (OverflowError, TypeError, ValueError):
                self.corrupt_rows_skipped += 1
                logger.warning(
                    "Skipping corrupt job metadata row %r",
                    row["job_id"],
                    exc_info=True,
                )
                continue
            result.append(persisted)
        return result

    def mark_interrupted(self, active_statuses: Iterable[str]) -> int:
        conn = self._require_connection()
        statuses = tuple(active_statuses)
        if not statuses:
            return 0
        placeholders = ",".join("?" for _ in statuses)
        now = _utc_now_iso()
        with self._lock:
            cursor = conn.execute(
                f"""
                UPDATE jobs
                SET status='interrupted',
                    error='Job was interrupted by a service restart.',
                    error_code='INTERRUPTED', finished_at_utc=?, updated_at_utc=?
                WHERE status IN ({placeholders})
                """,
                (now, now, *statuses),
            )
            return int(cursor.rowcount)

    def delete_metadata(self, job_id: str) -> bool:
        conn = self._require_connection()
        with self._lock:
            cursor = conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
            return cursor.rowcount > 0

    def total_artifact_bytes(self) -> int:
        conn = self._require_connection()
        with self._lock:
            value = conn.execute(
                "SELECT COALESCE(SUM(artifact_size_bytes), 0) FROM jobs"
            ).fetchone()[0]
        return int(value or 0)

    def check(self) -> tuple[bool, str | None]:
        try:
            conn = self._require_connection()
            with self._lock:
                conn.execute("SELECT 1").fetchone()
            return True, None
        except (JobStoreError, sqlite3.DatabaseError) as exc:
            self.available = False
            self.degraded_reason = str(exc)
            return False, self.degraded_reason


def _validate_persisted_job(job: PersistedJob) -> None:
    if not job.job_id or not job.kind:
        raise ValueError("job_id and kind must be non-empty")
    if job.progress_done < 0 or job.progress_total < 0:
        raise ValueError("job progress must be non-negative")
    if job.progress_done > job.progress_total:
        raise ValueError("job progress done must not exceed total")
    if job.artifact_size_bytes < 0 or job.estimated_bytes < 0:
        raise ValueError("job byte counts must be non-negative")
    if not math.isfinite(job.cost) or job.cost <= 0:
        raise ValueError("job cost must be finite and positive")


def _decode_issues(value: Any) -> list[dict[str, Any]] | None:
    if value is None or value == "":
        return None
    raw = json.loads(value)
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError("issues_json must be a list of objects")
    return [dict(item) for item in raw]
