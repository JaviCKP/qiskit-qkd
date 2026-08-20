"""Authoritative, JSON-safe runtime provenance for simulation results."""

from __future__ import annotations

import hashlib
import os
import platform as platform_module
import re
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import lru_cache
from importlib import import_module, metadata
from pathlib import Path
from typing import Any

from ._json import JSONObject, JSONValue, normalize_json_object, normalize_json_value

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


def _utc_now() -> str:
    """Return an unambiguous, timezone-aware UTC timestamp."""

    return datetime.now(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def canonical_json(value: Any) -> str:
    """Serialize a scenario or JSON-like value canonically.

    ``Scenario`` already exposes the canonical digest used by the package.  The
    helper intentionally accepts mappings too, which keeps artifact creation
    usable with archived scenarios and lightweight test doubles.
    """

    from ._json import dumps_canonical

    to_dict = getattr(value, "to_dict", None)
    payload = to_dict() if callable(to_dict) else value
    if not isinstance(payload, Mapping):
        raise TypeError("canonical JSON requires a mapping or to_dict() object")
    return dumps_canonical(payload)


def scenario_provenance(scenario: Any) -> JSONObject:
    """Return canonical scenario JSON and its SHA-256 digest."""

    encoded = canonical_json(scenario)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    # Scenario.digest() intentionally omits the wire schema marker.  Preserve
    # that scientific identity when available instead of hashing transport
    # metadata from ``to_dict``.
    scientific_digest = getattr(scenario, "digest", None)
    if callable(scientific_digest):
        candidate = scientific_digest()
        if isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{64}", candidate):
            digest = candidate
    return {
        "canonical_json": encoded,
        "digest": digest,
    }


def extract_seeds(value: Any) -> dict[str, JSONValue]:
    """Collect every JSON value whose field name contains ``seed``.

    Paths are retained so callers can distinguish a scenario seed from a
    backend, simulator, transpiler, or post-processing seed.  Duplicate values
    at different paths are intentionally not collapsed: the manifest records
    all available provenance, without guessing which seed was authoritative.
    """

    seeds: dict[str, JSONValue] = {}

    def walk(item: Any, path: str) -> None:
        to_dict = getattr(item, "to_dict", None)
        if callable(to_dict):
            try:
                item = to_dict()
            except Exception:
                return
        if isinstance(item, Mapping):
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else str(key)
                if "seed" in str(key).lower():
                    try:
                        seeds[child_path] = normalize_json_value(
                            child, path=child_path
                        )
                    except (TypeError, ValueError):
                        # A non-JSON RNG object is not provenance we can safely
                        # persist; leave it absent instead of inventing a value.
                        pass
                walk(child, child_path)
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                walk(child, f"{path}[{index}]")

    walk(value, "")
    return dict(sorted(seeds.items()))


def _git_root(start: Path | None = None) -> Path | None:
    candidate = (start or _PACKAGE_ROOT).resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for parent in (candidate, *candidate.parents):
        if (parent / ".git").exists():
            return parent
    return None


def vcs_provenance(root: str | os.PathLike[str] | None = None) -> JSONObject:
    """Describe VCS identity, including stale generated version metadata.

    This function never fabricates a commit.  A checkout without Git reports
    ``commit='unknown'`` unless the generated package metadata carries one, and
    labels that fallback with lower confidence.  A dirty checkout is explicit.
    """

    repo = _git_root(Path(root) if root is not None else None)
    generated = getattr(_build_version, "__commit__", None)
    generated = generated.strip() if isinstance(generated, str) else None
    generated_normalized = generated.removeprefix("g") if generated else None
    source = "unavailable"
    commit = "unknown"
    dirty: bool | None = None
    git_available = repo is not None
    git_error: str | None = None
    if repo is not None:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            commit = result.stdout.strip() or "unknown"
            status = subprocess.run(
                ["git", "-C", str(repo), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            )
            dirty = bool(status.stdout.strip())
            source = "git"
        except (OSError, subprocess.CalledProcessError) as exc:
            git_available = False
            git_error = str(exc)
    if commit == "unknown" and generated_normalized:
        commit = generated_normalized
        source = "setuptools_scm" if generated_normalized else "unavailable"
        dirty_value = getattr(_build_version, "__dirty__", False)
        dirty = dirty_value if isinstance(dirty_value, bool) else None
    mismatch = bool(
        commit != "unknown"
        and generated_normalized
        and generated_normalized.lower() != commit.lower()
    )
    confidence = (
        "high"
        if source == "git" and not mismatch
        else "medium"
        if source == "git"
        else "low"
        if source == "setuptools_scm"
        else "none"
    )
    payload: JSONObject = {
        "commit": commit,
        "dirty": dirty,
        "source": source,
        "confidence": confidence,
        "commit_confidence": confidence,
        # A generated _version.py commit is useful provenance but cannot be
        # verified once the checkout is unavailable (or has since changed).
        "commit_verified": source == "git" and not mismatch,
        "metadata_stale": source != "git" and generated_normalized is not None,
        "git_available": git_available,
        "version_metadata_commit": generated_normalized or "unknown",
        "version_metadata_source": getattr(
            _build_version, "__vcs_metadata_source__", "unavailable"
        ),
        "metadata_mismatch": mismatch,
    }
    if git_error:
        payload["git_error"] = git_error
    return payload


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
