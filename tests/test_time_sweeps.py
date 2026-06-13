from __future__ import annotations

from qiskit_qkd.analysis import sweep_bb84_time
from qiskit_qkd.config import DynamicConfig, ParameterSchedule, Scenario
from qiskit_qkd.results import Metrics, SimulationResult
from qiskit_qkd.temporal import ConstantProfile


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
                    profile=ConstantProfile(start_s=0.0, end_s=3.0, value=0.04),
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
    assert [row["seed"] for row in rows] == [100, 101, 102, 103]
    assert rows[0]["channel.depolarizing_probability"] == 0.04
    assert rows[2]["channel.depolarizing_probability"] == 0.0
    assert rows[0]["qber"] == 0.04
    assert rows[2]["qber"] == 0.0
    assert protocol.scenarios[0].channel.depolarizing_probability == 0.04
    assert protocol.scenarios[2].channel.depolarizing_probability == 0.0
