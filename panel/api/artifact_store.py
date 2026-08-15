"""Atomic, bounded-on-disk storage for job result artifacts.

Results are deliberately kept out of the jobs SQLite metadata database.  The
store writes a temporary file, fsyncs it, then replaces the final path so a
reader can never observe a partially-written JSON document.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class ArtifactStoreError(RuntimeError):
    """Base class for artifact storage failures."""


class ArtifactCorruptError(ArtifactStoreError):
    """Raised when an artifact is missing, malformed, or fails its digest."""


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    path: str
    digest: str
    size_bytes: int


class ArtifactStore:
    """Store JSON artifacts in a directory below a configured root."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve(strict=True)
        self.available = self.root.is_dir() and os.access(self.root, os.R_OK | os.W_OK)
        self.degraded_reason: str | None = None
        if not self.available:
            self.degraded_reason = f"artifact directory is not writable: {self.root}"

    def _path_for(self, job_id: str) -> Path:
        if not isinstance(job_id, str) or not _SAFE_JOB_ID.fullmatch(job_id):
            raise ArtifactStoreError(f"invalid artifact job_id {job_id!r}")
        path = (self.root / f"{job_id}.json").resolve(strict=False)
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactStoreError(
                f"artifact path escaped root for job {job_id!r}"
            ) from exc
        return path

    def write_json(self, job_id: str, payload: Any) -> ArtifactRef:
        path = self._path_for(job_id)
        if not self.available:
            raise ArtifactStoreError(
                self.degraded_reason or "artifact store unavailable"
            )
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ArtifactStoreError(
                f"result for job {job_id!r} is not JSON serializable: {exc}"
            ) from exc
        digest = hashlib.sha256(encoded).hexdigest()
        fd, temporary = tempfile.mkstemp(
            prefix=f".{job_id}.", suffix=".tmp", dir=self.root
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            try:
                directory_fd = os.open(self.root, os.O_RDONLY)
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except OSError as exc:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise ArtifactStoreError(
                f"could not atomically write artifact for job {job_id!r}: {exc}"
            ) from exc
        return ArtifactRef(path=str(path), digest=digest, size_bytes=len(encoded))

    def read_json(self, job_id: str, *, digest: str | None = None) -> Any:
        path = self._path_for(job_id)
        try:
            encoded = path.read_bytes()
        except OSError as exc:
            raise ArtifactCorruptError(
                f"artifact for job {job_id!r} is unavailable: {exc}"
            ) from exc
        actual = hashlib.sha256(encoded).hexdigest()
        if digest is not None and actual != digest:
            raise ArtifactCorruptError(
                f"artifact digest mismatch for job {job_id!r}: expected {digest}, "
                f"got {actual}"
            )
        try:
            return json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactCorruptError(
                f"artifact for job {job_id!r} contains invalid JSON"
            ) from exc

    def reference_existing(self, job_id: str) -> ArtifactRef:
        """Validate and describe an artifact left between two metadata commits."""

        path = self._path_for(job_id)
        try:
            encoded = path.read_bytes()
        except OSError as exc:
            raise ArtifactCorruptError(
                f"artifact for job {job_id!r} is unavailable: {exc}"
            ) from exc
        try:
            json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactCorruptError(
                f"artifact for job {job_id!r} contains invalid JSON"
            ) from exc
        return ArtifactRef(
            path=str(path),
            digest=hashlib.sha256(encoded).hexdigest(),
            size_bytes=len(encoded),
        )

    def delete(self, job_id: str) -> bool:
        path = self._path_for(job_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ArtifactStoreError(
                f"could not remove artifact for job {job_id!r}: {exc}"
            ) from exc
        return True

    def check(self) -> tuple[bool, str | None]:
        """Return accessibility without raising from health endpoints."""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".health-probe"
            probe.write_bytes(b"ok")
            probe.unlink()
        except OSError as exc:
            self.available = False
            self.degraded_reason = f"artifact directory check failed: {exc}"
            return False, self.degraded_reason
        self.available = True
        self.degraded_reason = None
        return True, None
