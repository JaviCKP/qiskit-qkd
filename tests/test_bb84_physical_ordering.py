from __future__ import annotations

import random

import pytest

from qiskit_qkd import (
    ChannelConfig,
    EveConfig,
    PreparedState,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.backends import QiskitSamplerBackend
from qiskit_qkd.eavesdroppers import EveAttackResult
from qiskit_qkd.protocols import BB84Protocol


def test_preparation_error_is_applied_once_before_no_eve() -> None:
    scenario = Scenario(
        pulses=256,
        clock_rate_hz=1_000_000.0,
        seed=41,
        source=SourceConfig(preparation_error_probability=1.0),
    )

    result = BB84Protocol().run(scenario)

    assert result.metrics.sifted > 80
    assert result.metrics.qber == pytest.approx(1.0)


def test_eve_receives_the_effective_prepared_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[PreparedState] = []

    class CaptureEve:
        def attack(self, *, prepared_state: PreparedState, **kwargs) -> EveAttackResult:
            del kwargs
            observed.append(prepared_state)
            return EveAttackResult(
                resend_bit=prepared_state.prepared_bit,
                resend_basis=prepared_state.alice_basis,
            )

    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.eve_from_config",
        lambda _config: CaptureEve(),
    )
    scenario = Scenario(
        pulses=32,
        clock_rate_hz=1_000_000.0,
        seed=7,
        source=SourceConfig(preparation_error_probability=1.0),
        eavesdropper=EveConfig(
            kind="intercept_resend",
            intercept_probability=0.0,
            attack_position="pre_loss",
        ),
    )

    BB84Protocol().run(scenario)

    assert observed
    assert all(state.preparation_error for state in observed)
    assert all(state.prepared_bit == 1 - state.alice_bit for state in observed)


def test_attack_position_roundtrip_preserves_default_and_serializes_pre_loss() -> None:
    default = Scenario(pulses=2, clock_rate_hz=1_000_000.0, seed=3)
    assert default.eavesdropper.attack_position == "post_loss"
    assert "attack_position" not in default.to_dict()["eavesdropper"]
    assert Scenario.from_json(default.to_json()) == default

    pre_loss = Scenario(
        pulses=2,
        clock_rate_hz=1_000_000.0,
        seed=3,
        eavesdropper=EveConfig(kind="pns", attack_position="pre_loss"),
    )
    assert pre_loss.to_dict()["eavesdropper"]["attack_position"] == "pre_loss"
    assert Scenario.from_json(pre_loss.to_json()) == pre_loss


def test_pns_pre_loss_sees_more_multiphoton_pulses_before_channel_loss() -> None:
    common = {
        "pulses": 500,
        "clock_rate_hz": 1_000_000.0,
        "seed": 123,
        "source": SourceConfig(kind="weak_coherent", mean_photon_number=3.0),
        "channel": ChannelConfig(kind="fiber", fixed_loss_db=10.0),
        "store_full_event_log": True,
    }
    pre_loss = BB84Protocol().run(
        Scenario(
            **common,
            eavesdropper=EveConfig(kind="pns", attack_position="pre_loss"),
        ),
    )
    post_loss = BB84Protocol().run(
        Scenario(
            **common,
            eavesdropper=EveConfig(kind="pns", attack_position="post_loss"),
        ),
    )

    pre_splits = sum(event.eve_action == "pns_split" for event in pre_loss.event_sample)
    post_splits = sum(
        event.eve_action == "pns_split" for event in post_loss.event_sample
    )
    assert pre_splits > post_splits
    assert pre_splits > 0


def test_prepared_batch_does_not_resample_preparation_error() -> None:
    state = PreparedState(
        alice_bit=0,
        alice_basis="Z",
        prepared_bit=1,
        preparation_error=True,
        preparation_error_applied=True,
    )
    backend = QiskitSamplerBackend(
        seed=19,
        preparation_error_probability=1.0,
    )

    assert backend.measure_bb84_prepared_batch([(state, "Z")]) == (1,)
    expected = random.Random(19 + 0x51A7E).random()
    assert backend._preparation_rng.random() == expected

    with pytest.raises(ValueError):
        PreparedState(alice_bit=2, alice_basis="Z", prepared_bit=0)
