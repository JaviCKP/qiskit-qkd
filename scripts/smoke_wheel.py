"""Install a wheel into an isolated temporary venv and exercise provenance.

By default this performs a normal end-user installation and a four-pulse BB84
run. ``--no-deps`` retains an offline import-only mode. The temporary
environment is always removed before the script exits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import venv
from pathlib import Path


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "wheel",
        type=Path,
        nargs="?",
        help="wheel produced by python -m build (defaults to the only dist/*.whl)",
    )
    parser.add_argument(
        "--no-deps",
        action="store_true",
        help="install only the wheel and construct a result without Qiskit execution",
    )
    parser.add_argument("--expected-package-version")
    parser.add_argument("--expected-commit")
    parser.add_argument(
        "--expected-dirty",
        choices=("true", "false"),
    )
    parser.add_argument("--expected-implementation-hash")
    args = parser.parse_args()

    if args.wheel is None:
        candidates = sorted(Path("dist").glob("*.whl"))
        if len(candidates) != 1:
            parser.error(
                "pass a wheel path when dist/ does not contain exactly one wheel"
            )
        wheel = candidates[0].resolve()
    else:
        wheel = args.wheel.resolve()
    if wheel.suffix != ".whl" or not wheel.is_file():
        parser.error(f"wheel path does not point to a .whl file: {wheel}")

    with tempfile.TemporaryDirectory(prefix="qiskit-qkd-wheel-") as scratch:
        root = Path(scratch)
        env_dir = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        python = env_dir / ("Scripts" if os.name == "nt" else "bin") / (
            "python.exe" if os.name == "nt" else "python"
        )
        install = [str(python), "-m", "pip", "install"]
        if args.no_deps:
            install.extend(("--no-deps", "--no-index"))
        install.append(str(wheel))
        _run(install)
        check = _import_only_smoke() if args.no_deps else _execution_smoke()
        smoke_env = os.environ.copy()
        smoke_env["PYTHONNOUSERSITE"] = "1"
        completed = subprocess.run(
            [str(python), "-c", check],
            cwd=root,
            env=smoke_env,
            check=True,
            capture_output=True,
            text=True,
        )
        provenance = json.loads(completed.stdout)
        _validate_provenance(provenance, args)
        print(json.dumps(provenance, sort_keys=True))
    return 0


def _execution_smoke() -> str:
    return """
import json
from qiskit_qkd import Scenario
from qiskit_qkd.protocols import BB84Protocol

scenario = Scenario(pulses=4, clock_rate_hz=1_000.0, seed=17)
result = BB84Protocol().run(scenario)
print(json.dumps(result.provenance, sort_keys=True))
"""


def _import_only_smoke() -> str:
    return """
import json
from qiskit_qkd import Metrics, Scenario, SimulationResult

scenario = Scenario(pulses=1, clock_rate_hz=1_000.0, seed=17)
result = SimulationResult(scenario=scenario, metrics=Metrics(pulses=1))
print(json.dumps(result.provenance, sort_keys=True))
"""


def _validate_provenance(
    provenance: object,
    args: argparse.Namespace,
) -> None:
    if not isinstance(provenance, dict):
        raise SystemExit("wheel smoke did not emit a provenance JSON object")
    required = {
        "python_version",
        "platform",
        "package_version",
        "commit",
        "dirty",
        "vcs_metadata_source",
        "qiskit_version",
        "qiskit_aer_version",
        "backend",
        "backend_source",
        "implementation_hash",
    }
    missing = sorted(required - provenance.keys())
    if missing:
        raise SystemExit(f"wheel provenance is missing fields: {', '.join(missing)}")
    for name in (
        "python_version",
        "platform",
        "package_version",
        "commit",
        "vcs_metadata_source",
        "qiskit_version",
        "backend",
        "backend_source",
    ):
        if not isinstance(provenance[name], str) or not provenance[name]:
            raise SystemExit(f"wheel provenance field {name!r} is not a string")
    if not isinstance(provenance["dirty"], bool):
        raise SystemExit("wheel provenance dirty field is not a bool")
    aer_version = provenance["qiskit_aer_version"]
    if aer_version is not None and not isinstance(aer_version, str):
        raise SystemExit("wheel provenance Aer version is neither string nor null")
    if re.fullmatch(r"[0-9a-f]{64}", provenance["implementation_hash"]) is None:
        raise SystemExit("wheel provenance implementation hash is not SHA-256")
    if provenance["package_version"] == "0.0.0":
        raise SystemExit("wheel retained the placeholder 0.0.0 version")
    if not args.no_deps:
        if provenance["backend_source"] != "runtime":
            raise SystemExit("wheel execution did not record a runtime backend")
        if provenance["qiskit_version"] == "unknown":
            raise SystemExit("wheel execution did not resolve Qiskit metadata")
    expected = {
        "package_version": args.expected_package_version,
        "commit": args.expected_commit,
        "implementation_hash": args.expected_implementation_hash,
    }
    for name, value in expected.items():
        if value is not None and provenance[name] != value:
            raise SystemExit(
                f"wheel provenance {name}={provenance[name]!r}, expected {value!r}"
            )
    if args.expected_dirty is not None:
        expected_dirty = args.expected_dirty == "true"
        if provenance["dirty"] is not expected_dirty:
            raise SystemExit(
                f"wheel provenance dirty={provenance['dirty']!r}, "
                f"expected {expected_dirty!r}"
            )


if __name__ == "__main__":
    raise SystemExit(main())
