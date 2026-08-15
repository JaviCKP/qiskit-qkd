# QKD benchmark report

Workload fingerprint: `4c02dcdb41b81fc0c0afe78b21d37788cdae2732dd4d09a915792597a031774c`

| Case | Median total (s) | RSD | Peak Python MiB | Circuits | Shots | Events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bb84_ideal | 0.326112 | 1.53% | 0.433 | 1024 | 1024 | 1024 |
| bb84_channel_detector | 0.309873 | 1.90% | 0.373 | 311 | 311 | 1024 |
| bb84_decoy | 0.620528 | 0.99% | 0.587 | 740 | 740 | 2048 |
| e91 | 0.205935 | 0.43% | 1.137 | 768 | 768 | 768 |
| sweep_one_axis | 0.287045 | 0.47% | 0.465 | 334 | 334 | 768 |
| sweep_series_repeats | 0.637252 | 0.63% | 0.777 | 654 | 654 | 1536 |
| statevector_no_noise | 0.028826 | 0.85% | 0.263 | 2048 | 2048 | 2048 |
| aer_noise | 0.119654 | 4.37% | 1.107 | 128 | 128 | 128 |
| poisson_large_mean | 0.014173 | 0.50% | 0.050 | 0 | 0 | 1000 |
