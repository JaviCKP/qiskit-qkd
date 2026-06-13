# Dynamic Parameters

Phase 4.1 adds dynamic communication conditions without adding plotting
dependencies. The library produces flat, JSON-safe rows that can later be sent
to matplotlib, pandas, notebooks, or a dashboard.

## Core API

Attach schedules to `Scenario.dynamic`:

```python
from qiskit_qkd import (
    ConstantProfile,
    DynamicConfig,
    EveConfig,
    ExponentialRampProfile,
    ParameterSchedule,
    Scenario,
)

scenario = Scenario(
    pulses=1_024,
    clock_rate_hz=1_000_000.0,
    seed=41,
    eavesdropper=EveConfig(kind="intercept_resend"),
    dynamic=DynamicConfig(
        parameter_schedules=(
            ParameterSchedule(
                target="eavesdropper.intercept_probability",
                profile=ConstantProfile(start_s=9.0, end_s=12.0, value=0.25),
            ),
            ParameterSchedule(
                target="source.preparation_error_probability",
                profile=ConstantProfile(start_s=0.0, end_s=3.0, value=0.08),
            ),
            ParameterSchedule(
                target="channel.background_count_rate_hz",
                profile=ExponentialRampProfile(
                    start_s=5.0,
                    end_s=8.0,
                    start_value=1_000.0,
                    end_value=200_000_000.0,
                    curve=3.0,
                ),
            ),
            ParameterSchedule(
                target="channel.classical_channel_power_mw",
                profile=ConstantProfile(start_s=10.0, end_s=12.0, value=3.0),
            ),
        ),
    ),
)
```

Resolve a concrete static scenario at a selected second:

```python
from qiskit_qkd import ParameterResolver

effective = ParameterResolver().scenario_at(scenario, time_s=6.5)
```

The base scenario remains unchanged. The effective scenario carries no pending
schedules (they are consumed by the resolution), so it can be passed directly
to protocol runners, backends, serializers, or analysis helpers.
`BB84Protocol.run()` and `E91Protocol.run()` reject scenarios that still carry
unresolved dynamic schedules instead of silently ignoring them; resolve the
scenario first or use `analysis.sweep_bb84_time()`.

## Supported Profiles

- `ConstantProfile(start_s, end_s, value)`: fixed value inside the window.
- `LinearRampProfile(start_s, end_s, start_value, end_value)`: straight-line
  interpolation.
- `ExponentialRampProfile(start_s, end_s, start_value, end_value, curve=4.0)`:
  exponential easing. Positive `curve` starts slowly and accelerates; negative
  `curve` starts quickly and saturates.

Profiles use closed windows:

```text
start_s <= time_s <= end_s
```

Outside the window, the scenario's base parameter value is used.

## Characterization Rows

Use `ChannelCharacterizer` when you want link-state rows without running a full
protocol:

```python
from qiskit_qkd import ChannelCharacterizer

rows = ChannelCharacterizer().characterize_time(
    scenario,
    time_points_s=[0.0, 2.0, 4.0, 6.5, 8.0],
)
```

Each row includes fields such as:

```text
time_s
distance_km
loss_db
transmittance
background_count_rate_hz
effective_background_count_rate_hz
raman_count_rate_hz
temporal_broadening_s
effective_jitter_std_s
channel_kind
geometric_transmittance
effective_beam_divergence_rad
atmospheric_loss_db
scattering_broadening_s
channel.background_count_rate_hz
channel.classical_channel_power_mw
source.preparation_error_probability
```

The dotted fields are the effective values of scheduled parameters. They are
flat on purpose so future plotting can choose columns directly.

## Temporal BB84 Sweeps

Use `sweep_bb84_time()` when you want protocol metrics at selected times:

```python
from qiskit_qkd import BB84Protocol, QiskitSamplerBackend
from qiskit_qkd.analysis import sweep_bb84_time

rows = sweep_bb84_time(
    BB84Protocol(),
    scenario,
    time_points_s=[0.0, 2.0, 4.0, 6.5, 8.0],
    backend_factory=lambda run_scenario: QiskitSamplerBackend(
        seed=run_scenario.seed,
        max_recorded_results=0,
    ),
)
```

Rows include `time_s`, `repeat`, `seed`, effective scheduled-parameter columns,
and standard metrics such as `qber`, `sifted`, `gain`, and
`secret_key_rate_bps`.

## Boundary

Dynamic schedules are an analysis/configuration layer. They do not make
`BB84Protocol.run()` secretly mutate parameters during a single run. This keeps
the protocol path reproducible and lets the same mechanism characterize other
communication scenarios in future phases.

Phase 5 also allows `eavesdropper.intercept_probability` as a scheduled target.
That makes it possible to compare quiet intervals with periods of partial
intercept-resend attack using the same temporal sweep machinery.

Phase 6.2 also allows PNS attack probabilities as numeric schedule targets:

```text
eavesdropper.pns_split_probability
eavesdropper.pns_block_single_photon_probability
```

Phase 6 decoy intensity tuples are static configuration in the current design.
Scalar source fields such as `source.mean_photon_number` can still be scheduled
for a single-intensity weak-coherent source, but individual entries inside
`source.decoy_intensities` are not mutable schedule targets yet.

Phase 6.1 fiber impairment scalars are also valid channel schedule targets:

```text
channel.pmd_coefficient_ps_sqrt_km
channel.chromatic_dispersion_ps_nm_km
channel.source_spectral_width_nm
channel.polarization_dependent_loss_db
channel.classical_channel_power_mw
channel.raman_coefficient_hz_mw_km
channel.raman_filter_isolation_db
```

Phase 8 optical-channel scalars are valid schedule targets as well:

```text
channel.wavelength_nm
channel.transmitter_aperture_m
channel.receiver_aperture_m
channel.beam_divergence_rad
channel.atmospheric_extinction_db_km
channel.scintillation_sigma
channel.pointing_jitter_rad
channel.underwater_extinction_m_inv
channel.underwater_scattering_broadening_ns_per_m
```

Categorical PDL axis fields (`pdl_axis_basis`, `pdl_axis_bit`) remain static so
time profiles stay numeric and easy to plot.
