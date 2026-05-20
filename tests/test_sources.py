from __future__ import annotations

import pytest

from qiskit_qkd.config import SourceConfig
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.sources import (
    EmissionEvent,
    IdealSinglePhotonSource,
    source_from_config,
)


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
