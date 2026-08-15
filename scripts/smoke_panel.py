"""Exercise the checkout-only panel API without starting a browser or server."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel.api.app import create_app  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="qiskit-qkd-panel-") as scratch:
        app = create_app(store_dir=Path(scratch), use_processes=False)
        with TestClient(app) as client:
            health = client.get("/api/health")
            if health.status_code != 200 or health.json().get("status") != "ok":
                raise SystemExit(
                    f"panel health smoke failed: {health.status_code} {health.text}"
                )
            openapi = client.get("/openapi.json")
            if openapi.status_code != 200 or "paths" not in openapi.json():
                raise SystemExit("panel OpenAPI smoke failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
