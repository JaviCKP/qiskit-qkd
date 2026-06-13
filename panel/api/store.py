from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class ExperimentStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        return [self._read(path) for path in sorted(self.root.glob("*.json"))]

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        path = self._path(experiment_id)
        if not path.exists():
            return None
        return self._read(path)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        experiment = dict(payload)
        experiment.setdefault("id", f"e_{uuid.uuid4().hex[:12]}")
        experiment.setdefault("created_at", datetime.now(UTC).isoformat())
        experiment["updated_at"] = datetime.now(UTC).isoformat()
        self._path(experiment["id"]).write_text(
            json.dumps(experiment, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return experiment

    def delete(self, experiment_id: str) -> bool:
        path = self._path(experiment_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, experiment_id: str) -> Path:
        safe_id = experiment_id.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe_id}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
