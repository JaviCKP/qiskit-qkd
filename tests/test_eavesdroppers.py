from __future__ import annotations

import random

import pytest

from qiskit_qkd import (
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    EveConfig,
    PostProcessingConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.eavesdroppers import (
    InterceptResendEve,
    NoEve,
    PhotonNumberSplittingEve,
    eve_from_config,
)
from qiskit_qkd.protocols import BB84Protocol


class IdealRandomBasisBackend:
    """Small deterministic backend that mimics ideal BB84 projective measures."""

    max_circuits_per_job = 256

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)
        self.batches: list[tuple[tuple[int, str, str], ...]] = []

    def measure_bb84_batch(
        self,
        rounds: list[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        batch = tuple(rounds)
        self.batches.append(batch)
        return tuple(
            bit if prepared_basis == bob_basis else self.rng.randrange(2)
            for bit, prepared_basis, bob_basis in batch
        )

    def provenance(self) -> dict[str, object]:
        return {"backend": "IdealRandomBasisBackend"}

    def qiskit_summary(self) -> dict[str, object]:
        return {"circuit_count": 0, "counts_sample": []}


class NoRandomRng:
    def random(self) -> float:
        raise AssertionError("zero-probability PNS attack must not sample RNG")


def test_eve_config_serializes_and_rejects_invalid_attack_parameters() -> None:
    scenario = Scenario(
        pulses=16,
        clock_rate_hz=1_000_000.0,
        seed=7,
        eavesdropper=EveConfig(
            kind="intercept_resend",
            intercept_probability=0.25,
        ),
    )

    restored = Scenario.from_json(scenario.to_json())

    assert restored.eavesdropper == scenario.eavesdropper
    assert restored.to_dict()["eavesdropper"] == {
        "kind": "intercept_resend",
        "intercept_probability": 0.25,
        "pns_split_probability": 1.0,
        "pns_block_single_photon_probability": 0.0,
    }
    assert isinstance(eve_from_config(restored.eavesdropper), InterceptResendEve)

    with pytest.raises(ValueError):
        EveConfig(kind="intercept_resend", intercept_probability=1.1)
    with pytest.raises(ValueError):
        EveConfig(kind="photon_number_splitting", pns_split_probability=-0.1)
    with pytest.raises(ValueError):
        EveConfig(kind="unknown")


def test_pns_eve_splits_multiphoton_pulses_without_changing_bb84_state() -> None:
    eve = PhotonNumberSplittingEve(
        split_probability=1.0,
        block_single_photon_probability=0.0,
    )

    result = eve.attack(
        bit=1,
        basis="X",
        basis_choices=("Z", "X"),
        rng=random.Random(5),
        photon_number=3,
        surviving_photon_number=2,
        intensity_class="signal",
    )

    assert result.intercepted is True
    assert result.eve_action == "pns_split"
    assert result.resend_bit == 1
    assert result.resend_basis == "X"
    assert result.eve_detectable is False
    assert result.eve_knows_alice_bit is True
    assert result.forwarded_photon_number == 1
    assert result.tags()["eve_photons_kept"] == 1


def test_pns_eve_does_not_create_forwarded_photons_after_channel_loss() -> None:
    eve = PhotonNumberSplittingEve(
        split_probability=1.0,
        block_single_photon_probability=0.0,
    )

    result = eve.attack(
        bit=1,
        basis="X",
        basis_choices=("Z", "X"),
        rng=random.Random(5),
        photon_number=3,
        surviving_photon_number=1,
        intensity_class="signal",
    )

    assert result.intercepted is False
    assert result.forwarded_photon_number is None


def test_pns_eve_with_zero_probabilities_does_not_consume_rng() -> None:
    eve = PhotonNumberSplittingEve(
        split_probability=0.0,
        block_single_photon_probability=0.0,
    )

    multiphoton = eve.attack(
        bit=1,
        basis="X",
        basis_choices=("Z", "X"),
        rng=NoRandomRng(),
        photon_number=3,
        surviving_photon_number=3,
        intensity_class="signal",
    )
    single_photon = eve.attack(
        bit=0,
        basis="Z",
        basis_choices=("Z", "X"),
        rng=NoRandomRng(),
        photon_number=1,
        surviving_photon_number=1,
        intensity_class="signal",
    )

    assert multiphoton.intercepted is False
    assert multiphoton.resend_bit == 1
    assert multiphoton.resend_basis == "X"
    assert single_photon.intercepted is False
    assert single_photon.resend_bit == 0
    assert single_photon.resend_basis == "Z"


def test_pns_eve_can_block_single_photon_pulses_to_mimic_loss() -> None:
    eve = PhotonNumberSplittingEve(
        split_probability=1.0,
        block_single_photon_probability=1.0,
    )

    result = eve.attack(
        bit=0,
        basis="Z",
        basis_choices=("Z", "X"),
        rng=random.Random(7),
        photon_number=1,
        surviving_photon_number=1,
        intensity_class="decoy",
    )

    assert result.intercepted is True
    assert result.eve_action == "pns_block_single"
    assert result.block_signal is True
    assert result.forwarded_photon_number == 0
    assert result.eve_knows_alice_bit is False
    assert result.tags()["eve_blocked_signal"] is True


def test_intercept_resend_records_resend_state_and_detectable_disturbance() -> None:
    eve = InterceptResendEve(intercept_probability=1.0)

    same_basis = eve.attack(
        bit=1,
        basis="Z",
        basis_choices=("Z",),
        rng=random.Random(3),
    )
    wrong_basis = eve.attack(
        bit=1,
        basis="Z",
        basis_choices=("X",),
        rng=random.Random(3),
    )

    assert same_basis.intercepted is True
    assert same_basis.resend_bit == 1
    assert same_basis.resend_basis == "Z"
    assert same_basis.eve_action == "intercept_resend"
    assert same_basis.eve_basis == "Z"
    assert same_basis.eve_detectable is False
    assert same_basis.eve_knows_alice_bit is True

    assert wrong_basis.intercepted is True
    assert wrong_basis.resend_basis == "X"
    assert wrong_basis.eve_basis == "X"
    assert wrong_basis.eve_detectable is True
    assert wrong_basis.eve_knows_alice_bit is False
    assert wrong_basis.tags()["eve_resend_basis"] == "X"


def test_no_eve_leaves_round_unchanged_and_records_no_trace() -> None:
    result = NoEve().attack(
        bit=0,
        basis="X",
        basis_choices=("Z", "X"),
        rng=random.Random(5),
    )

    assert result.intercepted is False
    assert result.resend_bit == 0
    assert result.resend_basis == "X"
    assert result.eve_action is None
    assert result.tags() == {}


def test_intercept_resend_bb84_increases_qber_and_tracks_eve_information() -> None:
    scenario = Scenario(
        pulses=2048,
        clock_rate_hz=1_000_000.0,
        seed=29,
        eavesdropper=EveConfig(
            kind="intercept_resend",
            intercept_probability=1.0,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        store_full_event_log=True,
    )

    result = BB84Protocol().run(
        scenario,
        backend=IdealRandomBasisBackend(seed=101),
    )

    intercepted = [
        event for event in result.event_sample if event.eve_action == "intercept_resend"
    ]
    detectable = [event for event in intercepted if event.eve_detectable]
    eve_known_sifted = [
        event for event in result.event_sample if event.tags.get("eve_knows_bit")
    ]

    assert result.metrics.transmitted == scenario.pulses
    assert result.metrics.eve_intercepted_fraction == 1.0
    assert 0.18 <= result.metrics.qber <= 0.32
    assert 0.4 <= result.metrics.eve_information_estimate <= 0.6
    assert len(intercepted) == scenario.pulses
    assert len(detectable) > 0
    assert len(eve_known_sifted) > 0
    assert intercepted[0].tags["eve_resend_basis"] in {"Z", "X"}


def test_pns_bb84_learns_multiphoton_sifted_bits_without_adding_qber() -> None:
    scenario = Scenario(
        pulses=4_096,
        clock_rate_hz=1_000_000.0,
        seed=43,
        source=SourceConfig(
            kind="weak_coherent",
            decoy_intensities=(
                DecoyIntensity("signal", 1.0, 1.0),
            ),
        ),
        channel=ChannelConfig(kind="fiber", distance_km=0.0, attenuation_db_km=0.0),
        detector=DetectorConfig(kind="threshold", efficiency=1.0),
        eavesdropper=EveConfig(
            kind="photon_number_splitting",
            pns_split_probability=1.0,
            pns_block_single_photon_probability=0.0,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        store_full_event_log=True,
    )

    result = BB84Protocol().run(
        scenario,
        backend=IdealRandomBasisBackend(seed=303),
    )

    pns_events = [
        event for event in result.event_sample if event.eve_action == "pns_split"
    ]
    known_sifted = [
        event
        for event in result.event_sample
        if event.sifted and event.tags.get("eve_knows_bit")
    ]

    assert pns_events
    assert known_sifted
    assert result.metrics.qber == 0.0
    assert result.metrics.eve_information_estimate > 0.0
