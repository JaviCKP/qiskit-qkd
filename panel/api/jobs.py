from __future__ import annotations

import multiprocessing
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any


@dataclass
class JobRecord:
    job_id: str
    kind: str
    status: str
    progress: dict[str, int]
    created_at: float
    future: Future[Any] | None = None
    result: Any = None
    error: str | None = None

    def to_status(self) -> dict[str, Any]:
        self.refresh()
        payload: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "elapsed_s": round(time.monotonic() - self.created_at, 3),
        }
        if self.status == "done":
            payload["result"] = self.result
        if self.error is not None:
            payload["error"] = self.error
        return payload

    def refresh(self) -> None:
        if self.future is None or self.status in {"done", "error", "cancelled"}:
            return
        if not self.future.done():
            self.status = "running"
            return
        try:
            self.result = self.future.result()
            self.status = "done"
            self.progress["done"] = self.progress["total"]
        except Exception as exc:  # pragma: no cover - defensive job boundary
            self.status = "error"
            self.error = str(exc)


class JobManager:
    def __init__(self, *, use_processes: bool = True) -> None:
        self._records: dict[str, JobRecord] = {}
        self._executor: ProcessPoolExecutor | ThreadPoolExecutor | None
        if use_processes:
            context = multiprocessing.get_context("spawn")
            self._executor = ProcessPoolExecutor(max_workers=1, mp_context=context)
        else:
            self._executor = None

    def submit(
        self,
        kind: str,
        fn: Callable[..., Any],
        *args: Any,
        total: int = 1,
    ) -> JobRecord:
        job_id = f"{kind[0]}_{uuid.uuid4().hex[:12]}"
        record = JobRecord(
            job_id=job_id,
            kind=kind,
            status="queued",
            progress={"done": 0, "total": total},
            created_at=time.monotonic(),
        )
        self._records[job_id] = record
        if self._executor is None:
            try:
                record.result = fn(*args)
                record.status = "done"
                record.progress["done"] = total
            except Exception as exc:  # pragma: no cover - exercised by API status
                record.status = "error"
                record.error = str(exc)
            return record
        record.future = self._executor.submit(fn, *args)
        return record

    def get(self, job_id: str) -> JobRecord | None:
        record = self._records.get(job_id)
        if record is not None:
            record.refresh()
        return record

    def cancel(self, job_id: str) -> bool:
        record = self._records.get(job_id)
        if record is None:
            return False
        record.refresh()
        if record.status in {"done", "error", "cancelled"}:
            return False
        if record.future is not None:
            record.future.cancel()
        record.status = "cancelled"
        return True

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(cancel_futures=True)
