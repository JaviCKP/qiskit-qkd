from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qiskit_qkd import Scenario
from qiskit_qkd.experiments import write_artifact
from qiskit_qkd.provenance import extract_seeds, scenario_provenance, vcs_provenance


def test_manifest_roundtrip_contains_canonical_scenario_and_csv_hash(
    tmp_path: Path,
) -> None:
    scenario = Scenario(pulses=8, clock_rate_hz=1_000.0, seed=41)
    script = tmp_path / "generate.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    paths = write_artifact(
        tmp_path / "artifact",
        name="run",
        rows=[{"seed": 41, "observed": 3, "scenario": scenario.to_dict()}],
        scenarios=[scenario],
        generator_path=script,
        command=["python", str(script)],
        repo_root=tmp_path,
        generated_at_utc="2026-01-01T00:00:00Z",
    )

    manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
    csv_bytes = paths.csv.read_bytes()
    assert manifest["generated_at_utc"] == "2026-01-01T00:00:00Z"
    assert manifest["scenario_digest"] == scenario.digest()
    assert manifest["scenario_canonical_json"] == scenario_provenance(scenario)[
        "canonical_json"
    ]
    assert manifest["csv"]["sha256"] == hashlib.sha256(csv_bytes).hexdigest()
    assert manifest["generator"]["sha256"] == hashlib.sha256(
        script.read_bytes()
    ).hexdigest()
    assert manifest["git"]["git_available"] is False


def test_seed_extraction_keeps_all_seed_paths() -> None:
    observed = extract_seeds(
        {
            "scenario": {"seed": 3},
            "backend": {"seed_simulator": 4, "seed_transpiler": None},
        }
    )
    assert observed == {
        "backend.seed_simulator": 4,
        "backend.seed_transpiler": None,
        "scenario.seed": 3,
    }


def test_vcs_provenance_explicitly_reports_no_git(tmp_path: Path) -> None:
    result = vcs_provenance(tmp_path)
    assert result["git_available"] is False
    assert result["source"] in {"setuptools_scm", "unavailable"}
    assert result["confidence"] in {"low", "none"}
