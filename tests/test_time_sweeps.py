from __future__ import annotations

import pytest

from qiskit_qkd.analysis import (
    sweep_bb84_distance,
    sweep_bb84_time,
    sweep_scenario_parameter,
)
from qiskit_qkd.config import ChannelConfig, DynamicConfig, ParameterSchedule, Scenario
from qiskit_qkd.results import Metrics, SimulationResult
from qiskit_qkd.temporal import LinearRampProfile


class RecordingProtocol:
    def __init__(self) -> None:
        self.scenarios: list[Scenario] = []

    def run(self, scenario: Scenario, backend=None) -> SimulationResult:
        self.scenarios.append(scenario)
        return SimulationResult(
            scenario=scenario,
            metrics=Metrics(
                pulses=scenario.pulses,
                qber=scenario.channel.depolarizing_probability,
                loss_db=scenario.channel.distance_km,
            ),
        )


def test_sweep_bb84_time_runs_effective_scenarios_and_returns_plot_ready_rows() -> None:
    scenario = Scenario(
        pulses=10,
        clock_rate_hz=1.0,
        seed=100,
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.depolarizing_probability",
                    profile=LinearRampProfile(
                        start_s=0.0,
                        end_s=3.0,
                        start_value=0.04,
                        end_value=0.08,
                    ),
                ),
            ),
        ),
    )
    protocol = RecordingProtocol()

    rows = sweep_bb84_time(
        protocol,
        scenario,
        time_points_s=[0.0, 4.0],
        repeats=2,
    )

    assert [row["time_s"] for row in rows] == [0.0, 0.0, 4.0, 4.0]
    assert [row["seed"] for row in rows] == [100, 101, 100, 101]
    assert rows[0]["channel.depolarizing_probability"] == 0.04
    assert rows[2]["channel.depolarizing_probability"] == 0.0
    assert rows[0]["qber"] is None
    assert rows[2]["qber"] is None
    assert rows[0]["qber_defined"] is False
    assert rows[2]["qber_defined"] is False
    assert rows[0]["qber_margin"] is None
    assert rows[2]["qber_margin"] is None
    assert protocol.scenarios[0].channel.depolarizing_probability == 0.04
    assert protocol.scenarios[2].channel.depolarizing_probability == 0.0


@pytest.mark.parametrize("invalid_repeats", [True, 1.0, 1.5])
def test_public_sweep_helpers_reject_non_integer_repeats(
    invalid_repeats: object,
) -> None:
    protocol = RecordingProtocol()
    scenario = Scenario(
        pulses=10,
        clock_rate_hz=1.0,
        seed=100,
        channel=ChannelConfig(kind="fiber", distance_km=1.0),
    )

    with pytest.raises(TypeError, match="repeats must be a positive integer"):
        sweep_bb84_distance(
            protocol,
            scenario,
            [1.0],
            repeats=invalid_repeats,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="repeats must be a positive integer"):
        sweep_bb84_time(
            protocol,
            scenario,
            [0.0, 1.0],
            repeats=invalid_repeats,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="repeats must be a positive integer"):
        sweep_scenario_parameter(
            protocol,
            scenario,
            "scenario.pulses",
            [10],
            repeats=invalid_repeats,  # type: ignore[arg-type]
        )
