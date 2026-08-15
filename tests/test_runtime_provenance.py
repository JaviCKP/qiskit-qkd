from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from qiskit_qkd import Metrics, Scenario, SimulationResult, __version__
from qiskit_qkd.backends import QiskitSamplerBackend
from qiskit_qkd.provenance import (
    RUNTIME_PROVENANCE_FIELDS,
    _hash_package_tree,
    _package_version,
    _version_vcs_metadata,
    implementation_hash,
    runtime_provenance,
)


def _result(*, provenance: dict[str, object] | None = None) -> SimulationResult:
    scenario = Scenario(pulses=4, clock_rate_hz=1_000.0, seed=19)
    return SimulationResult(
        scenario=scenario,
        metrics=Metrics(pulses=scenario.pulses),
        provenance={} if provenance is None else provenance,
    )


def test_new_result_has_authoritative_json_safe_runtime_provenance() -> None:
    provenance = _result().provenance

    assert RUNTIME_PROVENANCE_FIELDS <= provenance.keys()
    assert provenance["python_version"] == re.fullmatch(
        r"\d+\.\d+\.\d+.*",
        provenance["python_version"],
    ).group()
    assert isinstance(provenance["platform"], str)
    assert provenance["platform"]
    assert provenance["package_version"] == __version__
    assert isinstance(provenance["commit"], str)
    assert provenance["commit"]
    assert isinstance(provenance["dirty"], bool)
    assert provenance["vcs_metadata_source"] in {
        "setuptools_scm",
        "pep440_local",
        "unavailable",
    }
    assert isinstance(provenance["qiskit_version"], str)
    assert provenance["qiskit_version"]
    assert provenance["qiskit_aer_version"] is None or isinstance(
        provenance["qiskit_aer_version"],
        str,
    )
    assert provenance["backend"] == "unknown"
    assert provenance["backend_source"] == "unavailable"
    assert re.fullmatch(r"[0-9a-f]{64}", provenance["implementation_hash"])


def test_plain_custom_provenance_cannot_spoof_authoritative_runtime_fields() -> None:
    supplied = {
        "python_version": "spoofed-python",
        "platform": "spoofed-platform",
        "package_version": "999.0",
        "commit": "spoofed-commit",
        "dirty": "yes",
        "vcs_metadata_source": "spoofed-source",
        "qiskit_version": "999.0",
        "qiskit_aer_version": "999.0",
        "backend_source": "spoofed-source",
        "implementation_hash": "0" * 64,
    }

    provenance = _result(provenance=supplied).provenance
    conflicts = provenance["reserved_field_conflicts"]

    assert set(supplied) <= conflicts.keys()
    for name, provided in supplied.items():
        assert conflicts[name]["provided"] == provided
        assert conflicts[name]["authoritative"] == provenance[name]


def test_backend_seam_records_effective_backend_authoritatively() -> None:
    backend = QiskitSamplerBackend(seed=19)
    scenario = Scenario(pulses=4, clock_rate_hz=1_000.0, seed=19)

    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(pulses=scenario.pulses),
        provenance=backend.provenance(),
        qiskit=backend.qiskit_summary(),
    )

    assert result.provenance["backend"] == "QiskitSamplerBackend"
    assert result.provenance["backend_source"] == "runtime"
    assert "backend" not in result.provenance.get("reserved_field_conflicts", {})


def test_direct_backend_claim_is_preserved_as_producer_supplied() -> None:
    provenance = _result(provenance={"backend": "custom-backend"}).provenance

    assert provenance["backend"] == "custom-backend"
    assert provenance["backend_source"] == "producer_supplied"
    assert "backend" not in provenance.get("reserved_field_conflicts", {})


@pytest.mark.parametrize("schema_version", [1, 2])
def test_archives_without_runtime_fields_preserve_producer_metadata(
    schema_version: int,
) -> None:
    payload = _result().to_dict(schema_version=schema_version)
    payload["library_version"] = "0.4.2"
    payload["provenance"]["library_version"] = "0.4.2"
    for name in RUNTIME_PROVENANCE_FIELDS:
        payload["provenance"].pop(name, None)

    restored = SimulationResult.from_dict(payload)

    assert restored.library_version == "0.4.2"
    assert restored.provenance["library_version"] == "0.4.2"
    assert RUNTIME_PROVENANCE_FIELDS.isdisjoint(restored.provenance)
    unavailable = restored.provenance["archive_load"]["unavailable_fields"]
    assert RUNTIME_PROVENANCE_FIELDS <= set(unavailable)


def test_qiskit_aer_version_is_optional_without_importing_aer(monkeypatch) -> None:
    observed: list[str] = []

    def absent_aer(distribution: str) -> str:
        observed.append(distribution)
        if distribution == "qiskit-aer":
            raise metadata.PackageNotFoundError(distribution)
        return "2.4.1"

    monkeypatch.setattr(metadata, "version", absent_aer)

    absent = runtime_provenance()
    assert absent["qiskit_version"] == "2.4.1"
    assert absent["qiskit_aer_version"] is None
    assert observed == ["qiskit", "qiskit-aer"]

    monkeypatch.setattr(metadata, "version", lambda distribution: "0.17.2")
    present = runtime_provenance()
    assert present["qiskit_aer_version"] == "0.17.2"


def test_implementation_hash_is_deterministic_and_code_sensitive(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "nested").mkdir(parents=True)
        (root / "module.py").write_bytes(b"VALUE = 1\n")
        (root / "nested" / "other.py").write_bytes(b"VALUE = 2\n")
        (root / "_version.py").write_bytes(b"__version__ = 'different'\n")
        (root / "ignored.txt").write_bytes(b"not implementation code")

    baseline = _hash_package_tree(first)
    assert baseline == _hash_package_tree(second)

    (second / "_version.py").write_bytes(b"__version__ = 'changed'\n")
    (second / "ignored.txt").write_bytes(b"changed non-python file")
    assert baseline == _hash_package_tree(second)

    (second / "nested" / "other.py").write_bytes(b"VALUE = 3\n")
    assert baseline != _hash_package_tree(second)


def test_implementation_hash_is_cached(monkeypatch) -> None:
    import qiskit_qkd.provenance as provenance_module

    calls = 0
    original = provenance_module._hash_package_tree

    def counting_hash(root: Path) -> str:
        nonlocal calls
        calls += 1
        return original(root)

    monkeypatch.setattr(provenance_module, "_hash_package_tree", counting_hash)
    implementation_hash.cache_clear()
    try:
        assert implementation_hash() == implementation_hash()
        assert calls == 1
    finally:
        implementation_hash.cache_clear()


def test_implementation_hash_does_not_follow_symlinks(tmp_path: Path) -> None:
    package = tmp_path / "package"
    outside = tmp_path / "outside"
    package.mkdir()
    outside.mkdir()
    (package / "inside.py").write_bytes(b"VALUE = 1\n")
    (outside / "outside.py").write_bytes(b"SECRET = 2\n")
    baseline = _hash_package_tree(package)
    try:
        (package / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert _hash_package_tree(package) == baseline


def test_generated_version_metadata_takes_precedence(monkeypatch) -> None:
    import qiskit_qkd.provenance as provenance_module

    generated = SimpleNamespace(
        __commit__="gabc123",
        __dirty__=True,
        __vcs_metadata_source__="setuptools_scm",
    )
    monkeypatch.setattr(provenance_module, "_build_version", generated)
    monkeypatch.setattr(
        provenance_module,
        "PACKAGE_VERSION",
        "9.9+gdef456",
    )

    assert provenance_module._build_vcs_metadata() == (
        "gabc123",
        True,
        "setuptools_scm",
    )


def test_source_without_generated_version_uses_installed_metadata(monkeypatch) -> None:
    monkeypatch.setattr(metadata, "version", lambda distribution: "2.3.4")

    assert _package_version(None) == "2.3.4"


def test_source_without_generated_version_has_explicit_fallback(monkeypatch) -> None:
    def missing(distribution: str) -> str:
        raise metadata.PackageNotFoundError(distribution)

    monkeypatch.setattr(metadata, "version", missing)

    assert _package_version(None) == "0.1.dev0"


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.2.dev4+gabc123", ("gabc123", False, "pep440_local")),
        (
            "0.2.dev4+gabc123.d20260812",
            ("gabc123", True, "pep440_local"),
        ),
        ("1.0.0", ("unknown", False, "unavailable")),
        ("1.0.0+vendor.1", ("unknown", False, "unavailable")),
    ],
)
def test_pep440_vcs_fallback_is_strict_and_deterministic(
    version: str,
    expected: tuple[str, bool, str],
) -> None:
    assert _version_vcs_metadata(version) == expected
