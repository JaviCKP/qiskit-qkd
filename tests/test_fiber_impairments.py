from __future__ import annotations

from qiskit_qkd.channels import ChannelCharacterizer
from qiskit_qkd.channels.impairments import pdl_transmittance_factor
from qiskit_qkd.config import (
    ChannelConfig,
    DetectorConfig,
    DynamicConfig,
    ParameterSchedule,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from qiskit_qkd.protocols import BB84Protocol
from qiskit_qkd.temporal import ConstantProfile, ParameterResolver


class CountingBackend:
    def __init__(self) -> None:
        self.rounds: list[tuple[int, str, str]] = []
        self.max_circuits_per_job = 512

    def measure_bb84_batch(
        self,
        rounds: list[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        self.rounds.extend(rounds)
        return tuple(
            alice_bit if alice_basis == bob_basis else 0
            for alice_bit, alice_basis, bob_basis in rounds
        )

    def measure_bb84(self, bit: int, alice_basis: str, bob_basis: str) -> int:
        self.rounds.append((bit, alice_basis, bob_basis))
        return bit if alice_basis == bob_basis else 0

    def provenance(self) -> dict[str, object]:
        return {"backend": "CountingBackend"}

    def qiskit_summary(self) -> dict[str, object]:
        return {"circuit_count": len(self.rounds)}


class FailingBackend(CountingBackend):
    def measure_bb84_batch(
        self,
        rounds: list[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        raise AssertionError("backend must not run without transmitted signal")

    def measure_bb84(self, bit: int, alice_basis: str, bob_basis: str) -> int:
        raise AssertionError("backend must not run without transmitted signal")


def impairment_scenario(
    *,
    pulses: int = 512,
    seed: int = 501,
    channel: ChannelConfig | None = None,
    source: SourceConfig | None = None,
    timing: TimingConfig | None = None,
    dynamic: DynamicConfig | None = None,
    store_full_event_log: bool = False,
) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        source=source or SourceConfig(emission_probability=1.0),
        channel=channel
        or ChannelConfig(kind="fiber", distance_km=10.0, attenuation_db_km=0.0),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
        timing=timing or TimingConfig(),
        dynamic=dynamic or DynamicConfig(),
        store_full_event_log=store_full_event_log,
    )


def test_channel_config_serializes_fiber_impairment_parameters() -> None:
    scenario = impairment_scenario(
        channel=ChannelConfig(
            kind="fiber",
            distance_km=25.0,
            attenuation_db_km=0.2,
            pmd_coefficient_ps_sqrt_km=0.1,
            chromatic_dispersion_ps_nm_km=17.0,
            source_spectral_width_nm=0.2,
            polarization_dependent_loss_db=1.5,
            pdl_axis_basis="X",
            pdl_axis_bit=1,
            classical_channel_power_mw=2.0,
            raman_coefficient_hz_mw_km=150.0,
            raman_filter_isolation_db=30.0,
        ),
    )

    restored = Scenario.from_json(scenario.to_json())

    assert restored == scenario
    assert restored.channel.pmd_coefficient_ps_sqrt_km == 0.1
    assert restored.channel.chromatic_dispersion_ps_nm_km == 17.0
    assert restored.channel.source_spectral_width_nm == 0.2
    assert restored.channel.polarization_dependent_loss_db == 1.5
    assert restored.channel.pdl_axis_basis == "X"
    assert restored.channel.pdl_axis_bit == 1
    assert restored.channel.classical_channel_power_mw == 2.0
    assert restored.channel.raman_coefficient_hz_mw_km == 150.0
    assert restored.channel.raman_filter_isolation_db == 30.0


def test_pmd_and_chromatic_dispersion_increase_timing_discards() -> None:
    baseline = impairment_scenario(
        pulses=512,
        seed=503,
        channel=ChannelConfig(kind="fiber", distance_km=100.0, attenuation_db_km=0.0),
    )
    broadened = impairment_scenario(
        pulses=512,
        seed=503,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=100.0,
            attenuation_db_km=0.0,
            pmd_coefficient_ps_sqrt_km=1_000.0,
            chromatic_dispersion_ps_nm_km=17.0,
            source_spectral_width_nm=1.0,
        ),
    )

    baseline_result = BB84Protocol().run(baseline, backend=CountingBackend())
    broadened_result = BB84Protocol().run(broadened, backend=CountingBackend())

    assert baseline_result.metrics.detected == baseline.pulses
    assert baseline_result.metrics.timing_discards == 0
    assert broadened_result.metrics.timing_discards > 450
    assert broadened_result.metrics.detected < 80


def test_raman_crosstalk_adds_background_clicks_without_quantum_signal() -> None:
    scenario = impairment_scenario(
        pulses=128,
        seed=509,
        source=SourceConfig(emission_probability=0.0),
        channel=ChannelConfig(
            kind="fiber",
            distance_km=1.0,
            attenuation_db_km=0.0,
            classical_channel_power_mw=1.0,
            raman_coefficient_hz_mw_km=50_000_000_000.0,
            raman_filter_isolation_db=0.0,
        ),
        store_full_event_log=True,
    )

    result = BB84Protocol().run(scenario, backend=FailingBackend())

    assert result.metrics.emitted == 0
    assert result.metrics.transmitted == 0
    assert result.metrics.detected == scenario.pulses
    assert {event.detection_origin for event in result.event_sample} == {"background"}


def test_pdl_transmittance_factor_is_state_dependent_and_never_boosts_loss() -> None:
    channel = ChannelConfig(
        polarization_dependent_loss_db=3.0,
        pdl_axis_basis="Z",
        pdl_axis_bit=0,
    )
    min_factor = 10 ** (-3.0 / 10.0)

    assert pdl_transmittance_factor(
        channel,
        alice_bit=0,
        alice_basis="Z",
    ) == 1.0
    assert pdl_transmittance_factor(
        channel,
        alice_bit=1,
        alice_basis="Z",
    ) == min_factor
    assert pdl_transmittance_factor(
        channel,
        alice_bit=0,
        alice_basis="X",
    ) == (1.0 + min_factor) / 2.0


def test_pdl_changes_bb84_transmission_statistics() -> None:
    baseline = impairment_scenario(
        pulses=1024,
        seed=521,
        channel=ChannelConfig(kind="fiber", distance_km=0.0, attenuation_db_km=0.0),
    )
    pdl = impairment_scenario(
        pulses=1024,
        seed=521,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=0.0,
            attenuation_db_km=0.0,
            polarization_dependent_loss_db=120.0,
            pdl_axis_basis="Z",
            pdl_axis_bit=0,
        ),
    )

    baseline_result = BB84Protocol().run(baseline, backend=CountingBackend())
    pdl_result = BB84Protocol().run(pdl, backend=CountingBackend())

    assert baseline_result.metrics.transmitted == baseline.pulses
    assert 350 < pdl_result.metrics.transmitted < 700
    assert pdl_result.metrics.transmitted < baseline_result.metrics.transmitted


def test_dynamic_schedules_can_drive_fiber_impairment_parameters() -> None:
    scenario = impairment_scenario(
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.classical_channel_power_mw",
                    profile=ConstantProfile(start_s=5.0, end_s=8.0, value=2.5),
                ),
                ParameterSchedule(
                    target="channel.polarization_dependent_loss_db",
                    profile=ConstantProfile(start_s=5.0, end_s=8.0, value=1.0),
                ),
            ),
        ),
    )

    before = ParameterResolver().scenario_at(scenario, time_s=2.0)
    active = ParameterResolver().scenario_at(scenario, time_s=6.0)

    assert before.channel.classical_channel_power_mw == 0.0
    assert before.channel.polarization_dependent_loss_db == 0.0
    assert active.channel.classical_channel_power_mw == 2.5
    assert active.channel.polarization_dependent_loss_db == 1.0


def test_channel_characterizer_reports_impairment_columns_for_plotting() -> None:
    scenario = impairment_scenario(
        channel=ChannelConfig(
            kind="fiber",
            distance_km=100.0,
            attenuation_db_km=0.2,
            background_count_rate_hz=10.0,
            pmd_coefficient_ps_sqrt_km=10.0,
            chromatic_dispersion_ps_nm_km=17.0,
            source_spectral_width_nm=0.1,
            polarization_dependent_loss_db=3.0,
            classical_channel_power_mw=2.0,
            raman_coefficient_hz_mw_km=100.0,
            raman_filter_isolation_db=10.0,
        ),
        timing=TimingConfig(jitter_std_s=1e-12),
    )

    row = ChannelCharacterizer().characterize_time(
        scenario,
        time_points_s=[0.0],
    )[0]

    assert row["pmd_broadening_s"] > 0.0
    assert row["chromatic_broadening_s"] > 0.0
    assert row["temporal_broadening_s"] > row["pmd_broadening_s"]
    assert row["effective_jitter_std_s"] > scenario.timing.jitter_std_s
    assert row["pdl_min_transmittance"] < row["transmittance"]
    assert row["raman_count_rate_hz"] == 2_000.0
    assert row["effective_background_count_rate_hz"] == 2_010.0
