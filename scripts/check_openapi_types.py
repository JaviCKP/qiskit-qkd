"""Regenerate OpenAPI types into a temporary file and require zero diff.

The checked-in ``panel/web/src/api/schema.ts`` is only overwritten when the
caller explicitly passes ``--write``.  The default remains a read-only CI
check that fails when the API schema and generated TypeScript drift apart.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from difflib import unified_diff
from pathlib import Path

_OPENAPI_STORE_ENV = "QKD_OPENAPI_STORE_DIR"


def create_openapi_app():
    """Build the schema app without touching a developer's panel library."""
    from panel.api.app import create_app

    store_dir = os.environ.get(_OPENAPI_STORE_ENV)
    if not store_dir:
        raise RuntimeError(
            f"{_OPENAPI_STORE_ENV} must point to an isolated temporary directory"
        )
    return create_app(store_dir=Path(store_dir), use_processes=False)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_openapi(url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"uvicorn exited before startup (code {process.returncode})"
            )
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    raise TimeoutError(f"timed out waiting for {url}")


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _remove_runtime_tree(path: Path) -> None:
    """Remove the isolated app store, retrying transient Windows handles."""
    delay_s = 0.05
    for attempt in range(20):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 19:
                raise
            time.sleep(delay_s)
            delay_s = min(0.5, delay_s * 1.5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("panel/web/src/api/schema.ts"),
        help="checked-in schema to compare",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the checked-in schema with the generated contract",
    )
    args = parser.parse_args()
    schema = args.schema.resolve()
    if not schema.is_file():
        parser.error(f"schema file does not exist: {schema}")

    port = _free_port()
    url = f"http://127.0.0.1:{port}/openapi.json"
    repo_root = Path(__file__).resolve().parents[1]
    runtime = Path(tempfile.mkdtemp(prefix="qiskit-qkd-openapi-runtime-"))
    try:
        environment = os.environ.copy()
        environment[_OPENAPI_STORE_ENV] = str(runtime)
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "scripts.check_openapi_types:create_openapi_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=repo_root,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            _wait_for_openapi(url, process)
            with tempfile.TemporaryDirectory(prefix="qiskit-qkd-openapi-") as scratch:
                generated = Path(scratch) / "schema.ts"
                npx = "npx.cmd" if os.name == "nt" else "npx"
                subprocess.run(
                    [npx, "openapi-typescript", url, "-o", str(generated)],
                    cwd=repo_root / "panel" / "web",
                    check=True,
                )
                expected_text = schema.read_text(encoding="utf-8").replace(
                    "\r\n", "\n"
                )
                actual_text = generated.read_text(encoding="utf-8").replace(
                    "\r\n", "\n"
                )
                if expected_text != actual_text:
                    if args.write:
                        schema.write_text(
                            actual_text,
                            encoding="utf-8",
                            newline="\n",
                        )
                        print(f"updated {schema}")
                        return 0
                    diff = "".join(
                        unified_diff(
                            expected_text.splitlines(keepends=True),
                            actual_text.splitlines(keepends=True),
                            fromfile=str(schema),
                            tofile=str(generated),
                        )
                    )
                    print(diff, end="")
                    return 1
        finally:
            _stop(process)
    finally:
        _remove_runtime_tree(runtime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
