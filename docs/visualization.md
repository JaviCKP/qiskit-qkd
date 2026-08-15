# Visualization

Phase 9 adds optional visual analytics on top of the existing flat analysis
rows. The plotting layer is intentionally thin: simulations and estimators
produce JSON-safe data, `analysis` can enrich or aggregate those rows, and
`visualization` turns them into reproducible Matplotlib figures.

Install the optional plotting dependency when you want figures:

```powershell
python -m pip install -e ".[plot]"
```

The base package does not import Matplotlib. Importing `qiskit_qkd` remains
lightweight, and plotting functions raise a clear `ImportError` if the `plot`
extra is missing.

## Philosophy

Visualization is an analysis layer, not a new simulator path.

- Plot functions accept `SimulationResult`-derived rows, decoy rows, Bell rows,
  channel-characterization rows, or sweep rows.
- Plot functions return a Matplotlib `Figure`; they do not call `show()`.
- Saved figures are reproducible when the scenario seed and input rows are
  reproducible.
- Figures use labels and units from repository metric names.
- Scientific interpretation remains in `SimulationResult.assessment` and the
  docs. Plots do not add finite-key, composable, real-system, or
  device-independent claims.

## Derived Metrics

`qiskit_qkd.analysis` exposes helpers for richer comparison rows:

```python
from qiskit_qkd.analysis import (
    add_derived_metrics,
    metric_rows_from_results,
    secure_distance_limit,
    summarize_metric_rows,
)
```

`metric_rows_from_results(...)` flattens one or more `SimulationResult`
objects into rows containing scenario labels, aggregate metrics, selected
classical diagnostics, and derived metrics.

`add_derived_metrics(...)` copies existing rows and adds useful ratios when the
required counters are present:

```text
emission_fraction          emitted / pulses
transmission_fraction      transmitted / emitted
detected_fraction          detected / pulses
sifted_fraction            sifted / detected
error_fraction             errors / sifted
timing_discard_fraction    timing_discards / transmitted
privacy_efficiency         final_key_length / corrected_key_length
qber_margin                qber_abort_threshold - assessment QBER;
                           null when QBER is undefined
chsh_margin                chsh_s - 2
key_estimate_available     assessment key status is estimated_key_available
secure                     deprecated compatibility field; always false
```

The row-level `qber` is the assessment value and is null without a sample;
`legacy_qber` preserves the schema-v1 numeric placeholder separately. The
derived column named `secure` is retained for API compatibility only and is
always false. New consumers should display `data_status`, `key_status`,
`rate_estimate_status`, `key_estimate_available`, and `security_scope` instead
of relabelling a rate or legacy boolean as formal security.

`summarize_metric_rows(...)` aggregates repeated rows by one or more columns
and reports population mean, standard deviation, min, max, p05, p95, and a
finite-value count for each requested metric. It separates
`legacy_abort_fraction` from `threshold_decision_fraction` and reports the
number of available tri-state threshold decisions. These are descriptive
Monte Carlo summaries, not confidence intervals or hypothesis tests. With one
repetition, dispersion and percentile columns do not quantify uncertainty;
use multiple independent seeds and report the per-metric finite count.

`secure_distance_limit(...)` is also a legacy API name. It returns the largest
sampled distance only when the assessment reports an estimated key, an
available positive rate, defined QBER, no exceeded threshold, and no failed
verification. A positive schema-v1 rate plus `abort=False` is insufficient.
The result remains a grid-dependent pedagogical-rate diagnostic, not a
certified secure range or an interpolated physical limit.

## Generic Plots

The low-level plotting functions operate on row dictionaries:

```python
from qiskit_qkd.visualization import (
    plot_metric_grid,
    plot_metric_sweep,
    plot_stacked_counts,
    plot_threshold_curve,
    save_figure,
)
```

Use `plot_metric_sweep(...)` for one or more y metrics against a sweep column:

```python
fig = plot_metric_sweep(
    rows,
    x="distance_km",
    y=("secret_key_rate_bps", "qber", "gain"),
    log_y=("secret_key_rate_bps",),
    threshold_lines={"qber": (0.11,)},
)
save_figure(fig, "bb84_distance_summary.svg")
```

Use `plot_metric_grid(...)` for heatmaps such as distance versus dark-count
rate, or Alice/Bob setting correlations:

```python
fig = plot_metric_grid(
    rows,
    x="distance_km",
    y="dark_count_rate_hz",
    z="qber",
)
```

Use `plot_stacked_counts(...)` for count budgets such as emitted, transmitted,
detected, sifted, and final-key material.

## Recipes

Recipes package common QKD figures without hiding the input rows:

```python
from qiskit_qkd.visualization import (
    plot_bb84_distance_summary,
    plot_channel_comparison,
    plot_decoy_security_summary,
    plot_e91_chsh_summary,
    plot_eve_tradeoff,
    plot_timing_summary,
)
```

- `plot_bb84_distance_summary(rows)` plots secret rate, QBER, and gain over
  distance with a QBER threshold guide.
- `plot_channel_comparison(rows)` compares loss, gain, and secret rate for
  channel-family sweeps.
- `plot_decoy_security_summary(decoy_rows)` plots per-intensity gain and QBER.
- `plot_e91_chsh_summary(bell_rows, chsh_s=...)` plots an E91 setting
  correlation heatmap.
- `plot_eve_tradeoff(rows)` plots QBER, Eve information, and secret rate
  against Eve interception diagnostics.
- `plot_timing_summary(result)` plots timing-status counts from stored event
  samples.

Recipes do not run simulations or validate that rows share a model. Their
input restrictions are therefore part of the contract:

- Distance/channel/Eve recipes require the named numeric columns and should
  receive comparable rows generated under documented seed/version policies.
- `plot_decoy_security_summary` filters to `row_type="intensity"`; it does not
  plot or validate the asymptotic row named `security`.
- `plot_e91_chsh_summary` visualizes observed correlations and an optional
  supplied `S`; the figure adds no sample-size or significance analysis unless
  the caller annotates it.
- `plot_timing_summary(result)` counts only `result.event_sample`. Unless the
  full event log was stored, the bars describe that stored sample rather than
  all attempted pulses.

Curve/sweep recipes must also pass the capability checks before producing
those rows:

- A mean-photon-number axis is active only for a scalar weak-coherent source
  (`weak_coherent` or `decoy_weak_coherent`);
  explicit `decoy_intensities` shadow the top-level mean and require a
  decoy-specific target instead.
- Pointing jitter is active for the free-space (`free_space`, `atmospheric`,
  `satellite`) and underwater (`underwater`, `water`, `marine`) families, not
  for the stable-baseline vacuum-space (`space`, `deep_space`, `vacuum`) family.
- A time axis requires BB84, at least two distinct points, and a supported
  schedule that varies over them. A missing schedule, constant profile, or
  equal-endpoint profile is not an executable time-evolution recipe.

## Example

`examples/bb84_visualization.py` generates
`examples/figures/bb84_distance_summary.svg` when the `plot` extra is
installed. Without the extra, it exits successfully with an installation hint.

```powershell
python examples/bb84_visualization.py
```

The generated `examples/figures/` directory is ignored by Git so local figures
do not pollute commits.

## Boundaries

Phase 9 does not add dashboards, GUI state, notebook-only dependencies, CLI
commands, finite-key intervals, or automatic report generation. Those can be
layered on top of the same row and figure APIs later.
