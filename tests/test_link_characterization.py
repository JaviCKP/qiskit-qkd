from __future__ import annotations

import math

import pytest

from qiskit_qkd.analysis import SWEEPABLE_TARGETS, sweep_scenario_parameter
from qiskit_qkd.config import (
    ChannelConfig,
    DecoyIntensity,
    DetectorConfig,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from qiskit_qkd.detectors import detector_state_from_scenario
from qiskit_qkd.results import Metrics, SimulationResult
from qiskit_qkd.sources import source_state_from_scenario
from qiskit_qkd.timing import timing_state_from_scenario


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
                emitted=scenario.pulses,
                transmitted=scenario.pulses,
            ),
        )


def test_source_state_reports_decoy_poisson_probabilities() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=1_000.0,
        seed=1,
        source=SourceConfig(
            kind="decoy_weak_coherent",
            decoy_intensities=(
                DecoyIntensity("signal", 0.5, 0.8),
                DecoyIntensity("decoy", 0.1, 0.2),
            ),
            preparation_error_probability=0.01,
        ),
    )

    state = source_state_from_scenario(scenario)

    signal = state.decoy_probabilities[0]
    assert state.source_kind == "decoy_weak_coherent"
    assert state.preparation_error_probability == 0.01
    assert signal.name == "signal"
    assert signal.p_zero == pytest.approx(math.exp(-0.5))
    assert signal.p_one == pytest.approx(0.5 * math.exp(-0.5))
    assert signal.p_multi == pytest.approx(1.0 - math.exp(-0.5) * 1.5)
    assert signal.multi_photon_fraction_given_emission == pytest.approx(
        signal.p_multi / (1.0 - signal.p_zero),
    )
    assert state.mean_photon_rate_hz == pytest.approx(1_000.0 * (0.8 * 0.5 + 0.2 * 0.1))
    assert state.to_dict()["decoy_probabilities"][0]["p_multi"] == pytest.approx(
        signal.p_multi,
    )


def test_detector_state_reports_gate_probabilities_and_limits() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=1.0,
        seed=1,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=10.0,
            background_count_rate_hz=500.0,
            classical_channel_power_mw=2.0,
            raman_coefficient_hz_mw_km=10.0,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.8,
            dark_count_rate_hz=1_000.0,
            gate_width_s=2e-9,
            dead_time_s=5e-6,
            afterpulse_probability=0.02,
            readout_error_probability=0.03,
            double_click_policy="random",
        ),
    )

    state = detector_state_from_scenario(scenario)

    assert state.detector_kind == "threshold"
    assert state.p_dark_per_gate == pytest.approx(1.0 - math.exp(-1_000.0 * 2e-9))
    assert state.effective_background_count_rate_hz > 500.0
    assert state.p_background_per_gate == pytest.approx(
        1.0 - math.exp(-state.effective_background_count_rate_hz * 2e-9),
    )
    assert state.max_count_rate_hz == pytest.approx(200_000.0)
    assert state.to_dict()["double_click_policy"] == "random"


def test_timing_state_reports_in_gate_probability_and_walkoff() -> None:
    scenario = Scenario(
        pulses=20,
        clock_rate_hz=1_000_000.0,
        seed=1,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=25.0,
            pmd_coefficient_ps_sqrt_km=2.0,
        ),
        detector=DetectorConfig(gate_width_s=2e-9),
        timing=TimingConfig(
            propagation_delay_s=1e-6,
            jitter_std_s=3e-10,
            clock_offset_s=0.0,
            clock_drift_ppm=1_000.0,
        ),
    )

    state = timing_state_from_scenario(scenario)

    assert state.effective_jitter_std_s > scenario.timing.jitter_std_s
    assert state.in_gate_probability == pytest.approx(
        math.erf(
            state.gate_width_s
            / (2.0 * math.sqrt(2.0) * state.effective_jitter_std_s),
        ),
    )
    assert state.first_walkoff_slot == 2
    assert state.to_dict()["propagation_delay_s"] == 1e-6


def test_generic_sweep_runs_any_sweepable_target_with_metric_rows() -> None:
    scenario = Scenario(pulses=10, clock_rate_hz=1.0, seed=10)
    protocol = RecordingProtocol()

    rows = sweep_scenario_parameter(
        protocol,
        scenario,
        "channel.distance_km",
        [0.0, 5.0],
        repeats=2,
    )

    assert "scenario.pulses" in SWEEPABLE_TARGETS
    assert [row["channel.distance_km"] for row in rows] == [0.0, 0.0, 5.0, 5.0]
    assert [row["seed"] for row in rows] == [10, 11, 12, 13]
    assert rows[2]["loss_db"] == 5.0
    assert protocol.scenarios[2].channel.distance_km == 5.0
