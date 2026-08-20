"""Regression tests for the dynamic experiment helpers."""

from __future__ import annotations

import math

import pytest

from experiments import experimentos_dinamicos as dynamic
from qiskit_qkd import ChannelConfig, DetectorConfig, Scenario
from qiskit_qkd.backends import backend_from_scenario


def _scenario(**kwargs) -> Scenario:
    defaults = {
        "pulses": 256,
        "clock_rate_hz": 1_000_000.0,
        "seed": 17,
        "channel": ChannelConfig(kind="fiber", distance_km=0.0),
        "detector": DetectorConfig(kind="threshold", efficiency=1.0),
    }
    defaults.update(kwargs)
    return Scenario(**defaults)


def test_run_uses_canonical_backend_and_does_not_invent_zero_qber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Scenario] = []
    real_factory = dynamic.backend_from_scenario

    def recording_factory(scenario: Scenario):
        calls.append(scenario)
        return real_factory(scenario)

    monkeypatch.setattr(dynamic, "backend_from_scenario", recording_factory)
    result = dynamic.run(
        _scenario(channel=ChannelConfig(kind="fiber", fixed_loss_db=1_000.0))
    )

    assert calls and calls[0].seed == 17
    assert result["assessment"]["qber_defined"] is False
    assert result["qber_defined"] is False
    assert result["qber"] is None
    assert result["rate_estimate_status"] == "unavailable"
    assert result["verification_status"] == "not_applicable"
    assert isinstance(result["classical"], dict)
    assert isinstance(result["bell"], dict)


def test_run_backend_from_scenario_activates_aer_noise() -> None:
    pytest.importorskip("qiskit_aer")
    scenario = _scenario(
        channel=ChannelConfig(
            kind="fiber",
            distance_km=0.0,
            depolarizing_probability=0.25,
            phase_damping_probability=0.2,
        )
    )

    backend = backend_from_scenario(scenario)

    assert backend.seed == scenario.seed
    assert backend.seed_simulator == scenario.seed
    assert backend.noise_model is not None
    assert backend.noise_summary["components"] == [
        "channel_depolarizing",
        "channel_phase_damping",
    ]


def test_phase_rotation_pi_affects_x_only_and_does_not_restore_rate() -> None:
    result = dynamic.run(
        _scenario(
            pulses=1_000,
            channel=ChannelConfig(
                kind="fiber",
                distance_km=0.0,
                polarization_rotation_z_rad=math.pi,
            ),
        )
    )

    assert result["qber_defined"] is True
    assert result["qber"] == pytest.approx(0.5, abs=0.08)
    assert result["qber"] < 1.0
    assert result["rate_estimate_status"] == "unavailable"
    assert result["secret_bps"] is None
