from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .errors import ApiValidationError, validation_exception_handler
from .jobs import JobManager
from .routes import (
    characterize,
    dynamics,
    experiments,
    presets,
    runs,
    scenarios,
    sweeps,
)
from .store import ExperimentStore


def create_app(
    *,
    store_dir: str | Path | None = None,
    use_processes: bool = True,
) -> FastAPI:
    job_manager = JobManager(use_processes=use_processes)
    store = ExperimentStore(
        Path(store_dir) if store_dir is not None else Path("panel/store"),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.job_manager = job_manager
        app.state.store = store
        try:
            yield
        finally:
            job_manager.shutdown()

    app = FastAPI(title="qiskit-qkd panel", version="0.1.0", lifespan=lifespan)
    app.state.job_manager = job_manager
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiValidationError, validation_exception_handler)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "qiskit-qkd-panel"}

    app.include_router(scenarios.router)
    app.include_router(runs.router)
    app.include_router(sweeps.router)
    app.include_router(characterize.router)
    app.include_router(dynamics.router)
    app.include_router(experiments.router)
    app.include_router(presets.router)

    return app
