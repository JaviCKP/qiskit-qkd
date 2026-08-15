"""Authoritative, JSON-safe runtime provenance for simulation results."""

from __future__ import annotations

import hashlib
import os
import platform as platform_module
import re
from collections.abc import Mapping
from functools import lru_cache
from importlib import import_module, metadata
from pathlib import Path
from typing import Any

from ._json import JSONObject, JSONValue, normalize_json_object

try:
    _build_version = import_module(f"{__package__}._version")
except ModuleNotFoundError as error:
    if error.name != f"{__package__}._version":
        raise
    _build_version = None

_FALLBACK_VERSION = "0.1.dev0"

RUNTIME_PROVENANCE_FIELDS = frozenset(
    {
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
)

_PACKAGE_ROOT = Path(__file__).resolve().parent


def _package_version(build_metadata: object | None) -> str:
    if build_metadata is not None:
        value = getattr(build_metadata, "__version__", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    try:
        return metadata.version("qiskit-qkd")
    except metadata.PackageNotFoundError:
        return _FALLBACK_VERSION


PACKAGE_VERSION = _package_version(_build_version)


class _BackendProvenance(dict[str, JSONValue]):
    """Mapping carrying backend identity through the existing backend seam."""

    def __init__(self, backend_name: str, values: Mapping[str, Any]) -> None:
        super().__init__(normalize_json_object(values, path="backend provenance"))
        self._backend_name = backend_name


def backend_provenance(
    backend: object,
    values: Mapping[str, Any],
) -> JSONObject:
    """Return backend details with identity derived from the backend object.

    ``SimulationResult`` trusts the backend name only when it arrives through
    this seam. A plain user-provided mapping cannot claim an authoritative
    backend identity.
    """

    backend_name = type(backend).__name__.strip() or "unknown"
    normalized = normalize_json_object(values, path="backend provenance")
    normalized["backend"] = backend_name
    return _BackendProvenance(backend_name, normalized)


def trusted_backend_name(value: Mapping[str, Any]) -> str | None:
    """Return the backend identity carried by :func:`backend_provenance`."""

    if type(value) is not _BackendProvenance:
        return None
    name = value._backend_name
    return name if name else None


def runtime_provenance(
    *,
    backend: str = "unknown",
    backend_source: str = "unavailable",
) -> JSONObject:
    """Return authoritative environment and installed-code provenance."""

    backend_name = backend.strip() if isinstance(backend, str) else ""
    if not backend_name:
        backend_name = "unknown"
    commit, dirty, vcs_source = _build_vcs_metadata()
    return {
        "python_version": platform_module.python_version(),
        "platform": _platform_description(),
        "package_version": PACKAGE_VERSION,
        "commit": commit,
        "dirty": dirty,
        "vcs_metadata_source": vcs_source,
        "qiskit_version": _distribution_version("qiskit") or "unknown",
        "qiskit_aer_version": _distribution_version("qiskit-aer"),
        "backend": backend_name,
        "backend_source": backend_source,
        "implementation_hash": implementation_hash(),
    }


def _platform_description() -> str:
    parts = (
        platform_module.system() or "unknown-os",
        platform_module.release() or "unknown-release",
        platform_module.machine() or "unknown-machine",
    )
    return "-".join(parts)


def _build_vcs_metadata() -> tuple[str, bool, str]:
    value = getattr(_build_version, "__commit__", "unknown")
    dirty = getattr(_build_version, "__dirty__", False)
    source = getattr(_build_version, "__vcs_metadata_source__", "version")
    if (
        source == "setuptools_scm"
        and isinstance(value, str)
        and value.strip()
        and value.strip().lower() not in {"none", "unknown"}
        and isinstance(dirty, bool)
    ):
        return value.strip(), dirty, "setuptools_scm"
    return _version_vcs_metadata(PACKAGE_VERSION)


def _version_vcs_metadata(version: str) -> tuple[str, bool, str]:
    _public, separator, local = version.partition("+")
    if not separator:
        return "unknown", False, "unavailable"
    parts = tuple(part for part in re.split(r"[._-]+", local.lower()) if part)
    commit = next(
        (
            part
            for part in parts
            if re.fullmatch(r"g[0-9a-f]+", part) is not None
        ),
        "unknown",
    )
    dirty = any(re.fullmatch(r"d[0-9]{8}", part) is not None for part in parts)
    if commit == "unknown" and not dirty:
        return "unknown", False, "unavailable"
    return commit, dirty, "pep440_local"


def _distribution_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


@lru_cache(maxsize=1)
def implementation_hash() -> str:
    """Return a cached SHA-256 over installed Python implementation files."""

    return _hash_package_tree(_PACKAGE_ROOT)


def _hash_package_tree(package_root: Path) -> str:
    """Hash relative names and bytes of non-symlink Python modules."""

    root = package_root.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"package root is not a directory: {root}")
    digest = hashlib.sha256()
    for relative, path in _python_modules(root):
        name = relative.as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _python_modules(root: Path) -> tuple[tuple[Path, Path], ...]:
    modules: list[tuple[Path, Path]] = []
    for current_name, directory_names, file_names in os.walk(
        root,
        topdown=True,
        onerror=_raise_walk_error,
        followlinks=False,
    ):
        current = Path(current_name)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name != "__pycache__"
            and _is_package_directory(root, current / name)
        )
        for file_name in sorted(file_names):
            candidate = current / file_name
            if candidate.suffix != ".py" or candidate.name == "_version.py":
                continue
            if candidate.is_symlink():
                continue
            resolved = candidate.resolve(strict=True)
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            modules.append((relative, resolved))
    modules.sort(key=lambda item: item[0].as_posix())
    return tuple(modules)


def _is_package_directory(root: Path, candidate: Path) -> bool:
    is_junction = getattr(candidate, "is_junction", lambda: False)
    if candidate.is_symlink() or is_junction():
        return False
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return resolved.is_dir()


def _raise_walk_error(error: OSError) -> None:
    raise error
