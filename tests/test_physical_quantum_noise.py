from __future__ import annotations

from qiskit_qkd import ChannelConfig, Scenario, SourceConfig
from qiskit_qkd.protocols import BB84Protocol


def test_source_preparation_error_probability_changes_bb84_signal_bits() -> None:
    scenario = Scenario(
        pulses=256,
        clock_rate_hz=1_000_000.0,
        seed=41,
        source=SourceConfig(preparation_error_probability=1.0),
    )

    result = BB84Protocol().run(scenario)

    assert result.metrics.sifted > 80
    assert result.metrics.qber == 1.0
    assert result.qiskit["circuit_metadata_sample"][0]["preparation_error"] is True


def test_channel_polarization_rotation_probability_changes_bb84_signal_bits() -> None:
    scenario = Scenario(
        pulses=256,
        clock_rate_hz=1_000_000.0,
        seed=43,
        channel=ChannelConfig(polarization_rotation_y_rad=3.141592653589793),
    )

    result = BB84Protocol().run(scenario)

    assert result.metrics.sifted > 80
    assert result.metrics.qber > 0.35
    assert (
        result.qiskit["circuit_metadata_sample"][0]["channel_rotation_y_rad"]
        == 3.141592653589793
    )
