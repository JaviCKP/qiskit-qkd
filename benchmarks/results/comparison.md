# QKD benchmark comparison

Both runs used workload fingerprint
`4c02dcdb41b81fc0c0afe78b21d37788cdae2732dd4d09a915792597a031774c`, one
warmup, five measured repetitions, the same fixed seeds, Python 3.14.5,
Qiskit 2.4.1, and Qiskit Aer 0.17.2 on the same machine. Time is the median total;
variability is relative standard deviation (RSD). Memory is median peak Python
memory from `tracemalloc` and excludes some native Qiskit/Aer allocations.

| Case | Before (s) | After (s) | Time change | RSD before / after | Peak MiB before / after | Logical circuits before / after | Shots before / after | Observation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| BB84 ideal | 0.431158 | 0.326112 | **24.36% faster** | 1.17% / 1.53% | 1.923 / 0.433 | 1024 / 1024 | 1024 / 1024 | Quantum section 79.2% faster; bounded structural Statevector reuse. |
| BB84 channel/detector | 0.339115 | 0.309873 | **8.62% faster** | 3.55% / 1.90% | 0.599 / 0.373 | 311 / 311 | 311 / 311 | Quantum section 51.3% faster; detections and requested shots unchanged. |
| BB84 decoy | 0.693105 | 0.620528 | **10.47% faster** | 1.15% / 0.99% | 0.983 / 0.587 | 740 / 740 | 740 / 740 | Quantum section 59.1% faster; small-mean Poisson keeps the historical RNG path. |
| E91 | 0.335706 | 0.205935 | **38.66% faster** | 0.87% / 0.43% | 2.207 / 1.137 | 768 / 768 | 768 / 768 | Quantum section 82.8% faster; unused noiseless outcomes are omitted with compatible RNG consumption. |
| Sweep, one axis | 0.320272 | 0.287045 | **10.37% faster** | 1.03% / 0.47% | 0.978 / 0.465 | 334 / 334 | 334 / 334 | Quantum section 48.9% faster. |
| Sweep, series/repeats | 0.702169 | 0.637252 | **9.25% faster** | 0.12% / 0.63% | 1.119 / 0.777 | 654 / 654 | 654 / 654 | Quantum section 40.8% faster; evaluation count is unchanged. |
| Statevector, no noise | 0.213245 | 0.028826 | **86.48% faster** | 4.15% / 0.85% | 3.753 / 0.263 | 2048 / 2048 | 2048 / 2048 | Same deterministic output digest; quantum section 87.2% faster and structurally equivalent circuits share probabilities. |
| Aer noise | 0.125120 | 0.119654 | 4.37% lower | 1.25% / 4.37% | 1.104 / 1.107 | 128 / 128 | 128 / 128 | **No conclusive improvement:** the difference is within final-run variability; memory is unchanged within tracing noise. |
| Poisson, large mean | 0.253621 | 0.014173 | **94.41% faster** | 1.36% / 0.50% | 0.049 / 0.050 | 0 / 0 | 0 / 0 | Hoermann PTRS removes work proportional to the mean; the 0.001 MiB difference is noise. |

“Logical circuits” and shots describe the same requested scientific workload before
and after. On the optimized noiseless path, `constructed_circuit_count` plus bounded
cache hit/miss/eviction metrics separately expose the reduced physical construction
and probability-evaluation work. Full serialized digests may differ where additive
provenance/cache/assessment fields were introduced; regression tests compare the
scientific outcomes and RNG-sensitive sequences directly. The dedicated
Statevector case retains the exact full output digest.
