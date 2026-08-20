# Packaging and reproducible checks

The Python distribution is built from `src/` and is intentionally independent
of the local dashboard.  `panel/` remains checkout-only: its FastAPI service
and Vite assets are a development application, not part of the published
wheel. CI therefore tests the panel API from a checkout and builds the web
assets in the frontend job, while the wheel smoke tests only the Python
artifact.

## Reproducible Python environments

`uv.lock` is the reproducibility lock for every supported Python (3.12, 3.13,
and 3.14) and the optional `aer`, `plot`, `panel`, and `dev` extras.  It records
PyPI source URLs and hashes and keeps platform markers instead of freezing one
machine's wheel.  It was generated with `uv lock` from the ranges in
`pyproject.toml`; update it deliberately with `uv lock --upgrade`, review the
package and hash diff, then run the complete CI gates.

```text
uv sync --locked --extra aer --extra plot --extra panel --extra dev
uv run pytest --cov=src/qiskit_qkd --cov=panel/api --cov-branch --cov-report=term-missing --cov-fail-under=85
uv run ruff check .
```

The 85% branch threshold is a floor for the current scientific package and
panel API integration suite; the measured Windows baseline is 88%. Branch
coverage is required (rather than only line coverage) so new error/validation
paths cannot silently remain untested. The small margin absorbs supported
Python/platform differences, but the floor must not be lowered to mask a
regression.

`build` and `pytest-cov` are development-only dependencies used by those gates.
The only build-system addition is `setuptools-scm`, a small maintained tool
whose sole job is deriving the package version; none of these tools is imported
at runtime.

## Version and artifacts

`setuptools-scm` derives a PEP 440 version from Git and writes
`qiskit_qkd/_version.py` during a build. This generated file is ignored rather
than versioned, preventing one build from making the next clean build appear
dirty. Without the generated module, a source import first uses installed
distribution metadata and otherwise reports the explicit non-zero
`0.1.dev0` fallback. A wheel built from a dirty checkout observed a version
such as `0.1.dev29+gfe47075.d20260812`; two consecutive builds in a simulated
clean checkout both produced `0.1.dev29+gfe47075` with `dirty=false`. The
generated file is included in an sdist, so building/installing that sdist does
not require Git and retains the same version.

```text
python -m build --sdist --wheel
python scripts/smoke_wheel.py dist/qiskit_qkd-*.whl
```

`smoke_wheel.py` creates and removes a temporary virtual environment, performs
a normal wheel installation, runs a four-pulse BB84 simulation, and validates
the emitted runtime provenance. `--no-deps` is available for an offline
import-only artifact check.

## Panel and OpenAPI checks

From a checkout, install the locked Python extras and run
`python scripts/smoke_panel.py` for health/OpenAPI startup coverage.  From
`panel/web`, run `npm ci`, `npm test`, `npm run lint`, and `npm run build`.

`scripts/check_openapi_types.py` starts the checkout API, generates TypeScript
into a temporary directory with the already-installed `openapi-typescript`
binary, and compares it to `panel/web/src/api/schema.ts`.  It never overwrites
the checked-in schema; a non-zero diff is the hand-off signal for the contract
integration owner to regenerate it.

## CI matrix

`.github/workflows/ci.yml` runs Python tests, Ruff, and branch coverage on all
three supported Python versions, builds and smoke-installs a wheel, runs the
checkout-only panel smoke, and runs the frontend npm gates.  A separate API
contract job performs the temporary OpenAPI/types comparison.  Windows and
Linux jobs use the same Python scripts; no gate depends on a PowerShell-only
path.

## Runtime provenance

Every newly constructed `SimulationResult` adds authoritative, JSON-safe
runtime fields to its existing `provenance` object:

- `python_version`, `platform`, and `package_version` identify the interpreter,
  OS/release/architecture, and installed distribution without paths or user
  names.
- `commit`, `dirty`, and `vcs_metadata_source` come directly from the
  setuptools-scm version template when VCS information is available.
  Rebuilding a wheel from an sdist retains the PEP 440 local version but cannot
  recover `ScmVersion.node` directly, so the strict fallback accepts only
  setuptools-scm's `+g<hex>` commit and `.dYYYYMMDD` dirty markers and labels
  the source `pep440_local`. Versions without those markers report
  `commit="unknown"`, `dirty=false`, and `vcs_metadata_source="unavailable"`.
- `qiskit_version` uses installed distribution metadata. `qiskit_aer_version`
  is a string when the optional package is installed and `null` otherwise; the
  provenance path never imports Aer just to discover its version.
- `backend` is the effective backend. The built-in backend seam labels it with
  `backend_source="runtime"`; direct producer claims remain compatible and are
  labelled `producer_supplied`; absent claims become `unknown`/`unavailable`.
- `implementation_hash` is a cached SHA-256 over each installed package
  module's relative POSIX name and bytes. `_version.py`, symlinks,
  `__pycache__`, non-Python files, timestamps, and absolute paths are excluded,
  so identical checkout and wheel code hashes identically.

Runtime/version/hash fields other than the compatible `backend` producer claim
are reserved: conflicting caller values are kept under
`reserved_field_conflicts` beside their authoritative replacements. A direct
`backend` claim remains producer metadata; the built-in backend seam replaces
it only when it can identify the effective runtime backend. Historical
schema-v1/v2 files are not rewritten with today's runtime data; missing fields
remain absent and are listed in `provenance.archive_load.unavailable_fields`.

The sdist limitation is explicit for exact tagged versions: if their public
version has no `+g<hex>` local segment, an sdist-to-wheel rebuild has no commit
identifier to recover and therefore reports `unknown` rather than inventing
one.

## Thesis experiment artifacts

`qiskit_qkd.experiments.write_artifact(...)` is the persistence
boundary for versioned experiment outputs. It writes `<name>.json` (manifest)
and `<name>.csv` as an atomic pair; the pair is the reproducibility unit and
should be stored together. The manifest includes:

- UTC generation time, commit, dirty state, and `commit_confidence`/verification
  status (unknown is explicit when VCS evidence is unavailable);
- Python, Qiskit, and Qiskit Aer versions, plus every discovered seed path;
- canonical serialized scenarios and their SHA-256 digests;
- CSV row count and SHA-256, stable `result_id`/CSV-row coverage, and the
  serialized observations;
- generator script path and SHA-256, the exact command, and repository context.

The writer hashes the generated CSV and script and performs the two-file write
without leaving a manifest that points at a missing CSV. This artifact contract
is intentionally separate from in-memory `SimulationResult` serialization:
JSON result envelopes remain useful for interchange, while the manifest + CSV
captures the thesis run, code, environment, seeds, and observations as one
versioned record.
