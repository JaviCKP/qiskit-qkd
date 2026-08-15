# Reproducible performance benchmarks

These benchmarks are intentionally separate from the normal unit-test suite. They
exercise representative BB84, E91, sweep, Statevector, Aer, and Poisson paths with
fixed seeds and bounded workloads.

From the repository root, using the project environment:

```powershell
..\.venv\Scripts\python.exe benchmarks\qkd_benchmarks.py `
  --repeats 5 --warmups 1 `
  --output benchmarks\results\baseline.json `
  --markdown benchmarks\results\baseline.md
```

Run the same command after the final relevant code change, changing only the two
output names to `final.json` and `final.md`. The JSON records the workload
fingerprint, environment, individual samples, medians, standard deviations, traced
Python memory, circuits, shots, processed events, output size, and deterministic
output digests.

The checked-in results are `results/baseline.json`, `results/final.json`, and the
human-readable comparison in `results/comparison.md`. Logical circuit and shot
counts are kept stable to make output-work comparisons explicit; backend summaries
also expose constructed-circuit and Statevector-cache metrics for the optimized
implementation.

Timing categories are measured as follows:

- `scenario_build_s`: configuration and workload construction.
- `quantum_s`: time spent inside the Qiskit backend measurement methods, including
  circuit construction and primitive/Statevector execution.
- `classical_s`: protocol/sweep time outside those backend calls.
- `serialization_s`: canonical JSON serialization after execution.

`peak_python_mib` uses `tracemalloc`; it does not include every native allocation
inside Qiskit or Aer. Compare results only on the same machine and environment.
