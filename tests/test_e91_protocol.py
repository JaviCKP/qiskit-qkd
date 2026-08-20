from __future__ import annotations

from dataclasses import replace

import pytest

from qiskit_qkd import (
    ChannelConfig,
    ConstantProfile,
    DetectorConfig,
    DynamicConfig,
    E91Config,
    EveConfig,
    ParameterSchedule,
    PostProcessingConfig,
    ProtocolConfig,
    QiskitSamplerBackend,
    Scenario,
    SourceConfig,
    TimingConfig,
)
from qiskit_qkd.analysis import bell_rows_from_result
from qiskit_qkd.protocols import E91Protocol


class LegacyE91Backend:
    """Expose the existing all-emitted-rounds backend contract only."""

    def __init__(self, backend: QiskitSamplerBackend) -> None:
        self.backend = backend

    def configure_from_scenario(self, scenario: Scenario) -> None:
        self.backend.configure_from_scenario(scenario)

    def measure_e91_batch(self, rounds):
        return self.backend.measure_e91_batch(rounds)

    def provenance(self):
        return self.backend.provenance()

    def qiskit_summary(self):
        return self.backend.qiskit_summary()


def e91_scenario(
    *,
    seed: int = 91,
    pulses: int = 2_048,
    source_preparation_error: float = 0.0,
    depolarizing_probability: float = 0.0,
) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            emission_probability=1.0,
            preparation_error_probability=source_preparation_error,
        ),
        channel=ChannelConfig(
            kind="ideal",
            depolarizing_probability=depolarizing_probability,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        store_full_event_log=True,
    )


def test_e91_ideal_singlet_violates_chsh_and_extracts_key() -> None:
    scenario = e91_scenario()

    result = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(
            seed=scenario.seed,
            max_circuits_per_job=512,
            max_recorded_results=0,
        ),
    )

    assert result.metrics.detected == scenario.pulses
    assert result.metrics.sifted > 0
    assert result.metrics.qber == 0.0
    assert result.metrics.chsh_s is not None
    assert result.metrics.chsh_s > 2.5
    assert (
        result.classical["secret_rate_model"]
        == "pedagogical_bb84_asymptotic_qber_fraction"
    )
    assert result.bell["bell_violation"] is True
    assert result.bell["chsh_s"] == result.metrics.chsh_s
    assert result.bell["classical_bound"] == 2.0
    assert result.bell["observed_threshold_exceeded"] is True
    assert result.bell["bell_violation_legacy_projection_of"] == (
        "observed_threshold_exceeded"
    )
    assert result.bell["bell_violation_legacy_none_maps_to"] is False
    assert "bell_violation_legacy_alias_of" not in result.bell
    assert result.classical["classical_bound"] == 2.0
    assert result.classical["observed_threshold_exceeded"] is True
    assert result.classical["bell_violation"] is True
    assert "bell_violation_legacy_alias_of" not in result.classical
    assert {
        row["setting_pair"]
        for row in result.bell["setting_rows"]
        if row["used_for_chsh"]
    } == {"A0/B0", "A0/B1", "A1/B0", "A1/B1"}
    rows = bell_rows_from_result(result)
    assert len(rows) == 6
    assert all("correlation" in row for row in rows)


def test_e91_marks_no_chsh_conclusion_without_coincidences() -> None:
    scenario = replace(
        e91_scenario(seed=92, pulses=32),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
    )

    result = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(seed=scenario.seed, max_recorded_results=0),
    )

    assert result.bell["chsh_sample_size"] == 0
    assert result.bell["observed_chsh_s"] is None
    assert result.bell["classical_bound"] == 2.0
    assert result.bell["observed_threshold_exceeded"] is None
    assert result.bell["bell_violation"] is False
    assert result.bell["bell_violation_legacy_projection_of"] == (
        "observed_threshold_exceeded"
    )
    assert result.bell["bell_violation_legacy_none_maps_to"] is False
    assert result.classical["observed_threshold_exceeded"] is None
    assert result.classical["classical_bound"] == 2.0
    assert result.classical["bell_violation"] is False
    assert result.classical["bell_violation_legacy_projection_of"] == (
        "observed_threshold_exceeded"
    )
    assert result.classical["bell_violation_legacy_none_maps_to"] is False


def test_e91_source_pair_preparation_error_reduces_chsh() -> None:
    ideal = E91Protocol().run(
        e91_scenario(seed=93),
        backend=QiskitSamplerBackend(seed=93, max_recorded_results=0),
    )
    noisy = E91Protocol().run(
        e91_scenario(seed=93, source_preparation_error=0.45),
        backend=QiskitSamplerBackend(seed=93, max_recorded_results=0),
    )

    assert ideal.metrics.chsh_s is not None
    assert noisy.metrics.chsh_s is not None
    assert noisy.metrics.chsh_s < ideal.metrics.chsh_s


def test_e91_channel_depolarizing_noise_reduces_chsh() -> None:
    pytest.importorskip("qiskit_aer")
    from qiskit_qkd.qiskit_integration import AerNoiseModelAdapter

    noisy_scenario = e91_scenario(seed=95, depolarizing_probability=0.35)
    noisy_adapter = AerNoiseModelAdapter.from_scenario(noisy_scenario)
    ideal = E91Protocol().run(
        e91_scenario(seed=95),
        backend=QiskitSamplerBackend(seed=95, max_recorded_results=0),
    )
    noisy = E91Protocol().run(
        noisy_scenario,
        backend=QiskitSamplerBackend(
            seed=95,
            seed_simulator=95,
            noise_model=noisy_adapter.noise_model,
            noise_summary=noisy_adapter.summary(),
            max_recorded_results=0,
        ),
    )

    assert ideal.metrics.chsh_s is not None
    assert noisy.metrics.chsh_s is not None
    assert noisy.metrics.chsh_s < ideal.metrics.chsh_s


def test_e91_protocol_auto_applies_aer_noise_from_scenario() -> None:
    pytest.importorskip("qiskit_aer")

    ideal = E91Protocol().run(e91_scenario(seed=96))
    noisy = E91Protocol().run(e91_scenario(seed=96, depolarizing_probability=0.35))

    assert ideal.metrics.chsh_s is not None
    assert noisy.metrics.chsh_s is not None
    assert noisy.metrics.chsh_s < ideal.metrics.chsh_s
    assert noisy.qiskit["noise_model"]["components"] == ["channel_depolarizing"]


@pytest.mark.parametrize(
    ("pair_mean", "expected_emitted", "expect_multipair"),
    [
        (0.0, 0, False),
        (2.0, None, True),
        (None, None, True),
    ],
)
def test_e91_poisson_pair_emission_diagnostics(
    pair_mean: float | None,
    expected_emitted: int | None,
    expect_multipair: bool,
) -> None:
    scenario = replace(
        e91_scenario(seed=105, pulses=512),
        e91=E91Config(pair_emission_model="poisson", pair_mean=pair_mean),
    )

    first = E91Protocol().run(scenario)
    second = E91Protocol().run(scenario)
    diagnostics = first.qiskit["e91_effective_diagnostics"]

    assert first.metrics == second.metrics
    assert first.classical == second.classical
    assert diagnostics == second.qiskit["e91_effective_diagnostics"]
    assert diagnostics["pair_emission_model"] == "poisson"
    assert diagnostics["backend_simulates_multipair"] is False
    assert diagnostics["backend_measurement_model"] == (
        "single_bell_pair_representative"
    )
    assert diagnostics["multipair_model"] == "event_layer_poisson_bell_representative"
    if expected_emitted is not None:
        assert first.metrics.emitted == expected_emitted
        assert diagnostics["pair_count_total"] == expected_emitted
        assert diagnostics["multipair_slots"] == 0
    else:
        assert diagnostics["pair_mean"] == (2.0 if pair_mean is not None else 1.0)
        assert diagnostics["pair_count_total"] >= first.metrics.emitted
        assert (diagnostics["multipair_slots"] > 0) is expect_multipair


def test_e91_rejects_non_e91_scenarios() -> None:
    with pytest.raises(ValueError):
        E91Protocol().run(
            Scenario(
                pulses=16,
                clock_rate_hz=1_000_000.0,
                seed=97,
                protocol=ProtocolConfig(name="bb84"),
            ),
        )


def test_e91_rejects_eavesdropper_scenarios() -> None:
    scenario = replace(
        e91_scenario(pulses=16),
        eavesdropper=EveConfig(
            kind="intercept_resend",
            intercept_probability=1.0,
        ),
    )

    with pytest.raises(ValueError, match="eavesdropper"):
        E91Protocol().run(scenario)


def test_e91_rejects_unresolved_dynamic_schedules() -> None:
    scenario = replace(
        e91_scenario(pulses=16),
        dynamic=DynamicConfig(
            parameter_schedules=(
                ParameterSchedule(
                    target="channel.distance_km",
                    profile=ConstantProfile(start_s=0.0, end_s=1.0, value=5.0),
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="dynamic schedules"):
        E91Protocol().run(scenario)


def test_e91_channel_background_is_applied_only_to_bob_arm() -> None:
    scenario = Scenario(
        pulses=16,
        clock_rate_hz=1_000_000.0,
        seed=99,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            emission_probability=0.0,
        ),
        channel=ChannelConfig(
            kind="ideal",
            background_count_rate_hz=1_000_000_000.0,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1.0,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        store_full_event_log=True,
    )

    result = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(seed=scenario.seed, max_recorded_results=0),
    )

    assert result.metrics.detected == 0
    assert all(
        event.tags["alice_detection_origin"] == "none"
        for event in result.event_sample
    )
    assert all(
        event.tags["bob_detection_origin"] == "background"
        for event in result.event_sample
    )


def test_e91_nearest_assigned_signal_is_not_a_coincidence() -> None:
    scenario = Scenario(
        pulses=4,
        clock_rate_hz=1_000_000.0,
        seed=100,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            emission_probability=1.0,
        ),
        channel=ChannelConfig(kind="ideal"),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
        timing=TimingConfig(
            clock_offset_s=-1e-6,
            slot_assignment_policy="nearest",
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        store_full_event_log=True,
    )

    result = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(seed=scenario.seed, max_recorded_results=0),
    )

    nearest_events = [
        event
        for event in result.event_sample
        if event.timing_status == "assigned_nearest"
    ]

    assert nearest_events
    assert result.metrics.detected == 0
    assert all(event.detected is False for event in nearest_events)
    assert all(event.sifted is False for event in nearest_events)


def test_e91_omits_unconsumed_noiseless_rounds_without_changing_results() -> None:
    scenario = Scenario(
        pulses=512,
        clock_rate_hz=1_000_000.0,
        seed=104,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            preparation_error_probability=0.2,
        ),
        channel=ChannelConfig(kind="fiber", distance_km=25.0),
        detector=DetectorConfig(
            efficiency=0.8,
            dark_count_rate_hz=100.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )
    optimized_backend = QiskitSamplerBackend(seed=scenario.seed)
    legacy_delegate = QiskitSamplerBackend(seed=scenario.seed)

    optimized = E91Protocol().run(scenario, backend=optimized_backend)
    legacy = E91Protocol().run(
        scenario,
        backend=LegacyE91Backend(legacy_delegate),
    )

    assert optimized.metrics == legacy.metrics
    assert optimized.classical == legacy.classical
    assert optimized.bell == legacy.bell
    assert optimized.event_sample == legacy.event_sample == ()
    assert optimized.qiskit["circuit_count"] < legacy.qiskit["circuit_count"]
    assert optimized.qiskit["e91_omitted_circuit_count"] > 0
    assert optimized_backend._preparation_rng.random() == (
        legacy_delegate._preparation_rng.random()
    )
    assert optimized_backend._measurement_rng.random() == (
        legacy_delegate._measurement_rng.random()
    )


def test_e91_with_lossy_fiber_and_free_space_channels() -> None:
    # 1. Test E91 with FiberChannel containing PMD, CD, PDL, and Raman crosstalk
    fiber_scenario = Scenario(
        pulses=128,
        clock_rate_hz=1_000_000.0,
        seed=101,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            emission_probability=1.0,
        ),
        channel=ChannelConfig(
            kind="fiber",
            distance_km=5.0,
            attenuation_db_km=0.2,
            pmd_coefficient_ps_sqrt_km=2.0,
            chromatic_dispersion_ps_nm_km=17.0,
            source_spectral_width_nm=1.0,
            polarization_dependent_loss_db=1.0,
            classical_channel_power_mw=1.0,
            raman_coefficient_hz_mw_km=0.01,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.9,
            dark_count_rate_hz=100.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    result_fiber = E91Protocol().run(
        fiber_scenario,
        backend=QiskitSamplerBackend(seed=fiber_scenario.seed, max_recorded_results=0),
    )
    assert result_fiber.metrics.emitted == fiber_scenario.pulses
    assert 0 < result_fiber.metrics.transmitted < result_fiber.metrics.emitted
    assert 0 < result_fiber.metrics.detected < result_fiber.metrics.emitted
    assert result_fiber.metrics.loss_db == pytest.approx(1.0)

    # 2. Test E91 with FreeSpaceChannel containing scintillation and pointing jitter
    fs_scenario = Scenario(
        pulses=128,
        clock_rate_hz=1_000_000.0,
        seed=102,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            emission_probability=1.0,
        ),
        channel=ChannelConfig(
            kind="free_space",
            distance_km=10.0,
            wavelength_nm=850.0,
            transmitter_aperture_m=0.15,
            receiver_aperture_m=0.40,
            atmospheric_extinction_db_km=0.1,
            scintillation_sigma=0.2,
            pointing_jitter_rad=1e-6,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.9,
            dark_count_rate_hz=100.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    result_fs = E91Protocol().run(
        fs_scenario,
        backend=QiskitSamplerBackend(seed=fs_scenario.seed, max_recorded_results=0),
    )
    assert result_fs.metrics.emitted == fs_scenario.pulses
    assert 0 < result_fs.metrics.transmitted < result_fs.metrics.emitted
    assert 0 < result_fs.metrics.detected < result_fs.metrics.emitted
    assert result_fs.metrics.loss_db > 0.0

    # 3. Test E91 with UnderwaterChannel containing underwater extinction and scattering
    uw_scenario = Scenario(
        pulses=128,
        clock_rate_hz=1_000_000.0,
        seed=103,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(
            kind="entangled_pair",
            emission_probability=1.0,
        ),
        channel=ChannelConfig(
            kind="underwater",
            distance_km=0.1,
            underwater_extinction_m_inv=0.05,
            underwater_scattering_broadening_ns_per_m=0.01,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.9,
            dark_count_rate_hz=100.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    result_uw = E91Protocol().run(
        uw_scenario,
        backend=QiskitSamplerBackend(seed=uw_scenario.seed, max_recorded_results=0),
    )
    assert result_uw.metrics.emitted == uw_scenario.pulses
    assert result_uw.metrics.transmitted < result_uw.metrics.emitted // 8
    assert result_uw.metrics.detected <= result_uw.metrics.transmitted
    assert result_uw.metrics.loss_db > 20.0
