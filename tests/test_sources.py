from __future__ import annotations

import math
import random
import statistics

import pytest

from qiskit_qkd.config import DecoyIntensity, SourceConfig
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.sources import (
    EmissionEvent,
    IdealSinglePhotonSource,
    WeakCoherentDecoySource,
    source_from_config,
)


class CountingRandom(random.Random):
    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.random_calls = 0

    def random(self) -> float:
        self.random_calls += 1
        return super().random()


def test_ideal_single_photon_source_emits_one_photon_when_probability_is_one() -> None:
    source = IdealSinglePhotonSource(emission_probability=1.0)

    event = source.emit(rng=make_rng(7), time_s=1.25e-6)

    assert event == EmissionEvent(
        emitted=True,
        photon_number=1,
        time_s=1.25e-6,
        intensity_class=None,
    )


def test_ideal_single_photon_source_emits_vacuum_when_probability_is_zero() -> None:
    source = IdealSinglePhotonSource(emission_probability=0.0)

    event = source.emit(rng=make_rng(7), time_s=0.0)

    assert event.emitted is False
    assert event.photon_number == 0


def test_ideal_single_photon_source_is_reproducible_with_same_seed() -> None:
    source = IdealSinglePhotonSource(emission_probability=0.4)
    first_rng = make_rng(13)
    second_rng = make_rng(13)

    first = [
        source.emit(rng=first_rng, time_s=float(index)).to_dict()
        for index in range(8)
    ]
    second = [
        source.emit(rng=second_rng, time_s=float(index)).to_dict()
        for index in range(8)
    ]

    assert first == second


def test_source_from_config_builds_ideal_single_photon_source() -> None:
    source = source_from_config(SourceConfig(emission_probability=0.25))

    assert isinstance(source, IdealSinglePhotonSource)
    assert source.emission_probability == 0.25


def test_weak_coherent_small_mean_keeps_legacy_seed_sequence() -> None:
    source = WeakCoherentDecoySource(
        intensities=(DecoyIntensity("signal", 0.6, 1.0),),
    )

    rng = make_rng(123)
    photons = [
        source.emit(rng=rng, time_s=float(index)).photon_number
        for index in range(24)
    ]

    assert photons == [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
        1,
        1,
        0,
        0,
        0,
        1,
        1,
        0,
        0,
        1,
        2,
        0,
    ]


def test_large_mean_poisson_sampling_has_bounded_rng_work() -> None:
    source = WeakCoherentDecoySource(
        intensities=(DecoyIntensity("stress", 1_000.0, 1.0),),
    )
    rng = CountingRandom(41)

    event = source.emit(rng=rng, time_s=0.0)

    assert event.photon_number >= 0
    assert rng.random_calls <= 64


@pytest.mark.parametrize(
    ("mean_photon_number", "samples", "mean_relative_tolerance"),
    [
        (0.2, 40_000, 0.04),
        (30.0, 20_000, 0.015),
        (1_000.0, 10_000, 0.006),
    ],
)
def test_poisson_sampling_mean_and_variance_are_statistically_consistent(
    mean_photon_number: float,
    samples: int,
    mean_relative_tolerance: float,
) -> None:
    source = WeakCoherentDecoySource(
        intensities=(DecoyIntensity("signal", mean_photon_number, 1.0),),
    )
    rng = make_rng(20260809)

    values = [
        source.emit(rng=rng, time_s=float(index)).photon_number
        for index in range(samples)
    ]

    assert statistics.fmean(values) == pytest.approx(
        mean_photon_number,
        rel=mean_relative_tolerance,
    )
    assert statistics.pvariance(values) == pytest.approx(
        mean_photon_number,
        rel=0.08,
    )


def test_small_mean_poisson_distribution_matches_expected_bins() -> None:
    mean_photon_number = 0.6
    samples = 50_000
    source = WeakCoherentDecoySource(
        intensities=(DecoyIntensity("signal", mean_photon_number, 1.0),),
    )
    rng = make_rng(20260810)
    counts = [0, 0, 0]
    for index in range(samples):
        photons = source.emit(rng=rng, time_s=float(index)).photon_number
        if photons < len(counts):
            counts[photons] += 1

    expected = [
        math.exp(-mean_photon_number),
        mean_photon_number * math.exp(-mean_photon_number),
        (mean_photon_number**2 / 2.0) * math.exp(-mean_photon_number),
    ]
    for observed_count, expected_probability in zip(counts, expected, strict=True):
        assert observed_count / samples == pytest.approx(
            expected_probability,
            abs=0.01,
        )


def test_poisson_sampling_rejects_unmodelled_huge_mean() -> None:
    source = WeakCoherentDecoySource(
        intensities=(DecoyIntensity("stress", 1_000_000_000_001.0, 1.0),),
    )

    with pytest.raises(ValueError, match="mean_photon_number.*reduce"):
        source.emit(rng=make_rng(7), time_s=0.0)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: EmissionEvent(emitted=True, photon_number=0, time_s=0.0),
        lambda: EmissionEvent(emitted=False, photon_number=1, time_s=0.0),
        lambda: EmissionEvent(emitted=True, photon_number=-1, time_s=0.0),
        lambda: EmissionEvent(emitted=True, photon_number=1, time_s=-1.0),
        lambda: IdealSinglePhotonSource(emission_probability=1.1),
    ],
)
def test_source_validation_rejects_invalid_values(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()
