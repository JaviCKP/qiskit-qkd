import json
import os
import subprocess
import sys
from pathlib import Path

import qiskit_qkd


def test_package_exposes_version() -> None:
    assert qiskit_qkd.__version__
    assert qiskit_qkd.__version__ != "0.0.0"


def test_package_exposes_non_fiber_channel_classes_lazily() -> None:
    assert qiskit_qkd.SpaceChannel(distance_km=0.0).transmittance() == 1.0
    assert qiskit_qkd.FreeSpaceChannel(distance_km=0.0).transmittance() == 1.0
    assert qiskit_qkd.UnderwaterChannel(distance_km=0.0).transmittance() == 1.0


def test_package_exposes_fiber_and_ideal_channel_classes_lazily() -> None:
    assert qiskit_qkd.IdealChannel().transmittance() == 1.0
    assert qiskit_qkd.FiberChannel(distance_km=10.0).transmittance() < 1.0


def test_package_import_does_not_import_qiskit_runtime_modules() -> None:
    repo_src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_src)

    script = (
        "import json, sys; "
        "import qiskit_qkd; "
        "print(json.dumps({"
        "'qiskit': 'qiskit' in sys.modules, "
        "'qiskit_aer': 'qiskit_aer' in sys.modules, "
        "'version': qiskit_qkd.__version__"
        "}))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    observed = json.loads(completed.stdout)
    assert observed == {
        "qiskit": False,
        "qiskit_aer": False,
        "version": qiskit_qkd.__version__,
    }
