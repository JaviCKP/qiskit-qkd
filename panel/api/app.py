from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from qiskit_qkd.config import CapabilityError

from .errors import (
    ApiValidationError,
    capability_exception_handler,
    job_capacity_exception_handler,
    job_shutdown_exception_handler,
    request_validation_exception_handler,
    store_validation_exception_handler,
    validation_exception_handler,
)
from .jobs import JobCapacityError, JobManager, JobManagerShutdownError
from .limits import DEFAULT_OPERATIONAL_LIMITS, OperationalLimits
from .routes import (
    characterize,
    dynamics,
    experiments,
    presets,
    runs,
    scenarios,
    sweeps,
)
from .store import ExperimentStore, StoreValidationError


def create_app(
    *,
    store_dir: str | Path | None = None,
    use_processes: bool = True,
    operational_limits: OperationalLimits | None = None,
    job_store_dir: str | Path | None = None,
    artifact_dir: str | Path | None = None,
) -> FastAPI:
    limits = operational_limits or DEFAULT_OPERATIONAL_LIMITS
    experiment_root = Path(store_dir) if store_dir is not None else Path("panel/store")
    metadata_root = (
        Path(job_store_dir) if job_store_dir is not None else experiment_root
    )
    store = ExperimentStore(
        experiment_root,
    )
    job_manager = JobManager(
        use_processes=use_processes,
        store_dir=metadata_root,
        artifact_dir=artifact_dir,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.job_manager = job_manager
        app.state.store = store
        app.state.operational_limits = limits
        try:
            yield
        finally:
            job_manager.shutdown()

    app = FastAPI(title="qiskit-qkd panel", version="0.1.0", lifespan=lifespan)
    app.state.job_manager = job_manager
    app.state.store = store
    app.state.operational_limits = limits
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiValidationError, validation_exception_handler)
    app.add_exception_handler(CapabilityError, capability_exception_handler)
    app.add_exception_handler(JobCapacityError, job_capacity_exception_handler)
    app.add_exception_handler(
        JobManagerShutdownError,
        job_shutdown_exception_handler,
    )
    app.add_exception_handler(
        StoreValidationError,
        store_validation_exception_handler,
    )
    app.add_exception_handler(
        RequestValidationError,
        request_validation_exception_handler,
    )

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "service": "qiskit-qkd-panel"}

    @app.get("/api/health/live")
    def health_live() -> dict[str, str]:
        """Liveness is process-level and must not depend on storage health."""
        return {"status": "ok", "service": "qiskit-qkd-panel"}

    @app.get("/api/health/ready", response_model=None)
    def health_ready() -> object:
        """Readiness reports each dependency and returns 503 when degraded."""
        manager_state = job_manager.readiness()
        store_ok = store.root.is_dir() and os.access(
            store.root,
            os.R_OK | os.W_OK,
        )
        reasons = list(manager_state.get("reasons", []))
        if not store_ok:
            reasons.append("experiment store directory is not accessible")
        payload: dict[str, object] = {
            "status": (
                "ok" if not reasons and manager_state.get("ready") else "degraded"
            ),
            "ready": not reasons and bool(manager_state.get("ready")),
            "service": "qiskit-qkd-panel",
            "dependencies": {
                "experiment_store": store_ok,
                "job_manager": bool(manager_state.get("ready")),
                "queue": manager_state.get("queue", {}),
            },
            "reasons": sorted(set(reasons)),
        }
        if payload["ready"]:
            return payload
        return Response(
            content=json.dumps(payload),
            status_code=503,
            media_type="application/json",
        )

    app.include_router(scenarios.router)
    app.include_router(runs.router)
    app.include_router(sweeps.router)
    app.include_router(characterize.router)
    app.include_router(dynamics.router)
    app.include_router(experiments.router)
    app.include_router(presets.router)
    _mount_static_app(app)

    return app


def _mount_static_app(app: FastAPI) -> None:
    dist_dir = Path(__file__).resolve().parents[1] / "web" / "dist"
    if not dist_dir.exists():
        return
    try:
        dist_root = dist_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        return
    if not dist_root.is_dir():
        return

    assets_dir = dist_root / "assets"
    try:
        assets_root = assets_dir.resolve(strict=True)
    except (OSError, RuntimeError):
        assets_root = None
    if (
        assets_root is not None
        and assets_root.is_dir()
        and _path_is_within(assets_root, dist_root)
    ):
        app.mount(
            "/assets",
            StaticFiles(directory=assets_root, follow_symlink=False),
            name="assets",
        )

    @app.get("/{path:path}", include_in_schema=False)
    def serve_spa(path: str, request: Request) -> Response:
        raw_path = _raw_request_path(request, path)
        resolution = _resolve_spa_request(dist_root, raw_path)
        if resolution.unsafe:
            return Response(
                content="Not Found",
                status_code=404,
                media_type="text/plain",
            )
        if resolution.file is not None:
            return FileResponse(resolution.file)

        index_resolution = _resolve_spa_request(dist_root, "index.html")
        if index_resolution.file is None:
            return Response(
                content="Not Found",
                status_code=404,
                media_type="text/plain",
            )
        return FileResponse(index_resolution.file)


@dataclass(frozen=True)
class _SpaResolution:
    file: Path | None
    unsafe: bool


_MAX_SPA_DECODE_ROUNDS = 8
_MAX_SPA_PATH_LENGTH = 4096


def _raw_request_path(request: Request, fallback: str) -> str:
    raw_path = request.scope.get("raw_path")
    if isinstance(raw_path, bytes):
        try:
            return raw_path.decode("ascii")
        except UnicodeDecodeError:
            return "\x00"
    if isinstance(raw_path, str):
        return raw_path
    return fallback


def _canonicalize_spa_path(raw_path: str) -> tuple[tuple[str, ...], bool]:
    if not isinstance(raw_path, str) or len(raw_path) > _MAX_SPA_PATH_LENGTH:
        return (), True

    path = raw_path
    if path.startswith("/"):
        if path.startswith("//"):
            return (), True
        path = path[1:]
    if path.startswith("\\"):
        return (), True

    for _ in range(_MAX_SPA_DECODE_ROUNDS):
        lowered = path.casefold()
        if any(token in lowered for token in ("%2f", "%5c", "%00")):
            return (), True
        try:
            decoded = unquote(path, encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, ValueError):
            return (), True
        if decoded == path:
            break
        path = decoded
    else:
        return (), True

    if (
        not path
        or "%" in path
        or "\x00" in path
        or "\\" in path
        or path.startswith("/")
    ):
        return (), bool(path)

    windows_path = PureWindowsPath(path)
    if windows_path.drive or windows_path.root or PurePosixPath(path).is_absolute():
        return (), True

    segments = tuple(segment for segment in path.split("/") if segment)
    if not segments or any(segment in {".", ".."} for segment in segments):
        return (), bool(segments)
    return segments, False


def _resolve_spa_request(dist_dir: Path, raw_path: str) -> _SpaResolution:
    segments, unsafe = _canonicalize_spa_path(raw_path)
    if unsafe:
        return _SpaResolution(None, True)
    if not segments:
        return _SpaResolution(None, False)

    try:
        dist_root = dist_dir.resolve(strict=True)
        requested = dist_root.joinpath(*segments)
        resolved = requested.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return _SpaResolution(None, True)

    if not _path_is_within(resolved, dist_root):
        return _SpaResolution(None, True)

    try:
        if not resolved.is_file():
            return _SpaResolution(None, False)
    except OSError:
        return _SpaResolution(None, True)
    return _SpaResolution(resolved, False)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
