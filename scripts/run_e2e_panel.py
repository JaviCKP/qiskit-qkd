"""Start an isolated QKD panel API for Playwright.

The API serves the already-built ``panel/web/dist`` SPA.  A fresh temporary
store is supplied to the application so E2E runs never read or write the
developer's ``panel/store``.  The process uses the thread-backed job manager
to keep shutdown bounded and deterministic.
"""

from __future__ import annotations

import argparse
import atexit
import os
import shutil
import signal
import socket
import sys
import tempfile
from pathlib import Path
from types import FrameType

import uvicorn

# Executing this file by absolute path puts ``scripts`` (rather than the
# repository root) on ``sys.path``.  Add the known project root and its src
# layout explicitly so namespace-package imports work on every platform,
# including a checkout that has not been installed in editable mode.
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

_temporary_directory: tempfile.TemporaryDirectory[str] | None = None
_temporary_root: Path | None = None
_server: uvicorn.Server | None = None


def _cleanup() -> None:
    global _temporary_directory, _temporary_root
    if _temporary_directory is not None:
        _temporary_directory.cleanup()
        _temporary_directory = None
    if _temporary_root is not None and _temporary_root.exists():
        # ``TemporaryDirectory.cleanup`` can leave SQLite WAL files behind on
        # Windows when the server receives a console termination event.  The
        # root is our freshly-created temp directory, never a caller path.
        shutil.rmtree(_temporary_root, ignore_errors=True)
    _temporary_root = None


def _stop_server(_signum: int, _frame: FrameType | None) -> None:
    if _server is not None:
        _server.should_exit = True


def _assert_port_available(port: int) -> None:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(
            f"E2E port {port} is unavailable; choose QKD_E2E_PORT or stop "
            "the listener"
        ) from exc
    finally:
        probe.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serve",
        action="store_true",
        help="run the API until interrupted",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("QKD_E2E_PORT", "18180")),
        help="localhost port (also configurable with QKD_E2E_PORT)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.serve:
        raise SystemExit("run_e2e_panel.py requires --serve")
    if not 1 <= args.port <= 65_535:
        raise SystemExit(f"port must be between 1 and 65535, got {args.port}")
    _assert_port_available(args.port)
    dist_directory = Path(__file__).resolve().parents[1] / "panel" / "web" / "dist"
    if not (dist_directory / "index.html").is_file():
        raise SystemExit(
            "panel/web/dist/index.html is missing; run the web build before "
            "starting E2E"
        )

    run_token = os.environ.get("QKD_E2E_RUN_TOKEN", "manual")
    if (
        not 1 <= len(run_token) <= 64
        or not run_token.replace("-", "").replace("_", "").isascii()
        or not run_token.replace("-", "").replace("_", "").isalnum()
    ):
        raise SystemExit(
            "QKD_E2E_RUN_TOKEN must be 1-64 letters, numbers, underscores, or "
            "hyphens"
        )

    global _temporary_directory, _temporary_root, _server
    _temporary_directory = tempfile.TemporaryDirectory(
        prefix=f"qkd-panel-e2e-{run_token}-"
    )
    temporary_root = Path(_temporary_directory.name)
    _temporary_root = temporary_root
    experiment_store = temporary_root / "experiments"
    job_store = temporary_root / "jobs"
    artifacts = temporary_root / "artifacts"

    from panel.api.app import create_app

    app = create_app(
        store_dir=experiment_store,
        job_store_dir=job_store,
        artifact_dir=artifacts,
        use_processes=False,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level=os.environ.get("QKD_E2E_LOG_LEVEL", "warning"),
        access_log=False,
    )
    _server = uvicorn.Server(config)
    atexit.register(_cleanup)
    if threading_is_main_thread():
        signal.signal(signal.SIGINT, _stop_server)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _stop_server)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, _stop_server)
    try:
        _server.run()
    except KeyboardInterrupt:
        _server.should_exit = True
    finally:
        _server.should_exit = True
        _cleanup()
    return 0


def threading_is_main_thread() -> bool:
    """Avoid signal registration errors when embedded by a test harness."""

    import threading

    return threading.current_thread() is threading.main_thread()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
