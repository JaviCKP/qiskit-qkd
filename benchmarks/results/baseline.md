# QKD benchmark report

Workload fingerprint: `4c02dcdb41b81fc0c0afe78b21d37788cdae2732dd4d09a915792597a031774c`

| Case | Median total (s) | RSD | Peak Python MiB | Circuits | Shots | Events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bb84_ideal | 0.431158 | 1.17% | 1.923 | 1024 | 1024 | 1024 |
| bb84_channel_detector | 0.339115 | 3.55% | 0.599 | 311 | 311 | 1024 |
| bb84_decoy | 0.693105 | 1.15% | 0.983 | 740 | 740 | 2048 |
| e91 | 0.335706 | 0.87% | 2.207 | 768 | 768 | 768 |
| sweep_one_axis | 0.320272 | 1.03% | 0.978 | 334 | 334 | 768 |
| sweep_series_repeats | 0.702169 | 0.12% | 1.119 | 654 | 654 | 1536 |
| statevector_no_noise | 0.213245 | 4.15% | 3.753 | 2048 | 2048 | 2048 |
| aer_noise | 0.125120 | 1.25% | 1.104 | 128 | 128 | 128 |
| poisson_large_mean | 0.253621 | 1.36% | 0.049 | 0 | 0 | 1000 |
