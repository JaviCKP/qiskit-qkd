# Optical Channel Families

The channel layer now supports fiber and three non-fiber optical media:
`space`, `free_space`, and `underwater`. These models stay in the event layer:
they decide photon survival and timing broadening. They do not hide detector
effects or quantum-state errors inside the channel object.

## Deep Space

Use `ChannelConfig(kind="space")` for vacuum links such as inter-satellite or
deep-space optical QKD.

The model is diffraction-limited geometric loss plus fixed optical loss:

```text
theta = beam_divergence_rad                 if configured above zero
theta = 2.44 * wavelength_m / D_t           otherwise

D_beam(L) = D_t + theta * L_m
eta_geom = min(1, (D_r / D_beam(L))**2)
eta = eta_geom * 10 ** (-fixed_loss_db / 10)
```

Vacuum does not add absorption, scintillation, chromatic broadening, or
polarization noise in this first-order model. Coherent rotations and Aer noise
can still be configured explicitly on `ChannelConfig` when the experiment needs
to study them.

## Free Space And Satellite

Use `ChannelConfig(kind="free_space")` for atmospheric horizontal links,
uplinks, downlinks, and satellite-to-ground studies.

The deterministic baseline combines geometric and atmospheric extinction:

```text
eta_base =
  eta_geom
  * 10 ** (-(fixed_loss_db + atmospheric_extinction_db_km * distance_km) / 10)
```

`transmittance()` returns this stable baseline for characterization rows. During
protocol simulation, `sample_transmittance(rng)` adds optional per-pulse fading:

```text
f_scint ~ LogNormal(-sigma**2 / 2, sigma)
r_point ~ Rayleigh(pointing_jitter_rad * L_m)
f_point = exp(-2 * (r_point / beam_radius_m)**2)
eta_instant = clip01(eta_base * f_scint * f_point)
```

`scintillation_sigma=0` and `pointing_jitter_rad=0` disable those effects.

## Underwater

Use `ChannelConfig(kind="underwater")` for blue-green underwater optical links.
The model uses Beer-Lambert extinction in inverse meters because underwater QKD
is usually studied over meter-scale paths:

```text
eta_water =
  eta_geom
  * exp(-underwater_extinction_m_inv * distance_m)
  * 10 ** (-fixed_loss_db / 10)
```

Optional `scintillation_sigma` and `pointing_jitter_rad` are sampled the same
way as free-space fading. Underwater multiple scattering can also broaden the
arrival-time distribution:

```text
scattering_broadening_s =
  underwater_scattering_broadening_ns_per_m
  * distance_m
  * 1e-9
```

That width is combined with PMD and chromatic broadening in
`temporal_broadening_s`, then with detector jitter in `effective_jitter_std_s`.
The result is visible as timing discards when Bob's gate is too narrow.

## Configuration Fields

The non-fiber channel fields are:

- `wavelength_nm`
- `transmitter_aperture_m`
- `receiver_aperture_m`
- `beam_divergence_rad`
- `atmospheric_extinction_db_km`
- `scintillation_sigma`
- `pointing_jitter_rad`
- `underwater_extinction_m_inv`
- `underwater_scattering_broadening_ns_per_m`

All are JSON-serializable, validated at construction time, supported by dynamic
schedules, and exposed by `ChannelCharacterizer`.

## Boundary

These models are compact link-budget and timing models. They are useful for
QKD comparison studies and plots, but they are not full wave-optics propagation,
adaptive-optics correction, orbital geometry, weather modeling, or
wavelength-resolved underwater scattering. Quantum depolarization and dephasing
remain explicit Qiskit/Aer settings through `depolarizing_probability` and
`phase_damping_probability`.
