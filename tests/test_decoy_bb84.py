from __future__ import annotations

import math

import pytest

from qiskit_qkd import (
    DecoyIntensity,
    PostProcessingConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.analysis import decoy_rows_from_result
from qiskit_qkd.backends import QiskitSamplerBackend
from qiskit_qkd.detectors import DetectionResult
from qiskit_qkd.postprocessing import estimate_vacuum_weak_decoy_security
from qiskit_qkd.protocols import BB84Protocol
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.sources import (
    EmissionEvent,
    WeakCoherentDecoySource,
    source_from_config,
)


class EchoBackend:
    max_circuits_per_job = 512

    def measure_bb84_batch(
        self,
        rounds: list[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        return tuple(bit for bit, _alice_basis, _bob_basis in rounds)

    def provenance(self) -> dict[str, object]:
        return {"backend": "EchoBackend"}

    def qiskit_summary(self) -> dict[str, object]:
        return {}


class TwoPhotonSource:
    def emit(self, *, rng, time_s: float) -> EmissionEvent:
        return EmissionEvent(
            emitted=True,
            photon_number=2,
            time_s=time_s,
            intensity_class="signal",
        )


class LosslessCountingChannel:
    loss_db = 0.0

    def transmittance(self) -> float:
        return 1.0

    def transmit(self, _rng) -> bool:
        raise AssertionError("channel core should sample photon survival count")


class RecordingDetector:
    def __init__(self) -> None:
        self.signal_photon_numbers: list[int] = []

    def detect(
        self,
        *,
        signal_present: bool,
        signal_photon_number: int,
        measured_bit: int | None,
        rng,
        time_s: float | None = None,
        background_count_rate_hz: float = 0.0,
    ) -> DetectionResult:
        self.signal_photon_numbers.append(signal_photon_number)
        return DetectionResult(
            detected=signal_present,
            bob_bit=measured_bit if signal_present else None,
            detection_origin="signal" if signal_present else "none",
            detection_pattern="signal" if signal_present else "no_click",
        )


def decoy_source_config() -> SourceConfig:
    return SourceConfig(
        kind="weak_coherent",
        decoy_intensities=(
            DecoyIntensity(
                name="signal",
                mean_photon_number=0.6,
                selection_probability=0.70,
            ),
            DecoyIntensity(
                name="decoy",
                mean_photon_number=0.2,
                selection_probability=0.20,
            ),
            DecoyIntensity(
                name="vacuum",
                mean_photon_number=0.0,
                selection_probability=0.10,
            ),
        ),
    )


def test_decoy_source_config_serializes_and_validates_intensities() -> None:
    scenario = Scenario(
        pulses=128,
        clock_rate_hz=1_000_000.0,
        seed=7,
        source=decoy_source_config(),
    )

    restored = Scenario.from_json(scenario.to_json())

    assert restored.source == scenario.source
    assert restored.source.decoy_intensities[0].name == "signal"
    assert restored.source.decoy_intensities[2].mean_photon_number == 0.0

    with pytest.raises(ValueError):
        SourceConfig(
            kind="weak_coherent",
            decoy_intensities=(
                DecoyIntensity("signal", 0.5, 0.8),
                DecoyIntensity("decoy", 0.1, 0.1),
            ),
        )
    with pytest.raises(ValueError):
        SourceConfig(
            kind="weak_coherent",
            decoy_intensities=(
                DecoyIntensity("signal", 0.5, 0.5),
                DecoyIntensity("signal", 0.1, 0.5),
            ),
        )


def test_weak_coherent_source_samples_poisson_photon_numbers() -> None:
    source = WeakCoherentDecoySource(
        intensities=(
            DecoyIntensity(
                name="signal",
                mean_photon_number=0.5,
                selection_probability=1.0,
            ),
        ),
    )
    rng = make_rng(123)

    events = [source.emit(rng=rng, time_s=index * 1e-9) for index in range(10_000)]
    mean_photons = sum(event.photon_number for event in events) / len(events)
    emitted_fraction = sum(event.emitted for event in events) / len(events)

    assert mean_photons == pytest.approx(0.5, abs=0.03)
    assert emitted_fraction == pytest.approx(1.0 - math.exp(-0.5), abs=0.03)
    assert {event.intensity_class for event in events} == {"signal"}
    assert any(event.photon_number > 1 for event in events)


def test_vacuum_decoy_intensity_never_emits_photons() -> None:
    source = WeakCoherentDecoySource(
        intensities=(
            DecoyIntensity(
                name="vacuum",
                mean_photon_number=0.0,
                selection_probability=1.0,
            ),
        ),
    )

    events = [
        source.emit(rng=make_rng(index), time_s=float(index))
        for index in range(16)
    ]

    assert {event.intensity_class for event in events} == {"vacuum"}
    assert all(event.emitted is False for event in events)
    assert all(event.photon_number == 0 for event in events)


def test_source_from_config_builds_weak_coherent_decoy_source() -> None:
    source = source_from_config(decoy_source_config())

    assert isinstance(source, WeakCoherentDecoySource)
    assert [intensity.name for intensity in source.intensities] == [
        "signal",
        "decoy",
        "vacuum",
    ]


def test_bb84_decoy_run_reports_per_intensity_statistics() -> None:
    scenario = Scenario(
        pulses=4_096,
        clock_rate_hz=1_000_000.0,
        seed=31,
        source=decoy_source_config(),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
        store_full_event_log=True,
    )

    result = BB84Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(
            seed=scenario.seed,
            max_circuits_per_job=512,
            max_recorded_results=0,
        ),
    )

    decoy = result.decoy

    assert set(decoy) == {"signal", "decoy", "vacuum", "security"}
    intensity_rows = {
        key: row for key, row in decoy.items() if key != "security"
    }
    assert sum(row["pulses"] for row in intensity_rows.values()) == scenario.pulses
    assert decoy["signal"]["mean_photon_number"] == 0.6
    assert decoy["signal"]["multi_photon"] > 0
    assert decoy["signal"]["surviving_photons"] >= decoy["signal"]["transmitted"]
    assert decoy["signal"]["gain"] > decoy["decoy"]["gain"]
    assert decoy["vacuum"]["emitted"] == 0
    assert decoy["vacuum"]["surviving_photons"] == 0
    assert decoy["vacuum"]["transmitted"] == 0
    assert decoy["vacuum"]["gain"] == 0.0
    assert decoy["security"]["method"] == "vacuum_weak_asymptotic"
    assert decoy["security"]["single_photon_yield_lower_bound"] > 0.0
    assert decoy["security"]["single_photon_error_rate_upper_bound"] == 0.0
    assert decoy["security"]["secret_key_rate_bps"] > 0.0
    assert result.metrics.qber == 0.0
    assert {event.intensity_class for event in result.event_sample} == {
        "signal",
        "decoy",
        "vacuum",
    }


def test_bb84_decoy_security_estimate_can_be_disabled() -> None:
    scenario = Scenario(
        pulses=512,
        clock_rate_hz=1_000_000.0,
        seed=37,
        source=decoy_source_config(),
        post_processing=PostProcessingConfig(
            qber_abort_threshold=None,
            decoy_security_estimation_enabled=False,
        ),
    )

    result = BB84Protocol().run(scenario, backend=EchoBackend())

    assert set(result.decoy) == {"signal", "decoy", "vacuum"}


def test_decoy_rows_from_result_returns_plot_ready_flat_rows() -> None:
    scenario = Scenario(
        pulses=512,
        clock_rate_hz=1_000_000.0,
        seed=39,
        source=decoy_source_config(),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )
    result = BB84Protocol().run(scenario, backend=EchoBackend())

    rows = decoy_rows_from_result(result)

    assert {row["row_type"] for row in rows} == {"intensity", "security"}
    assert {
        row["intensity_class"]
        for row in rows
        if row["row_type"] == "intensity"
    } == {"signal", "decoy", "vacuum"}
    assert all("pulses" in row for row in rows if row["row_type"] == "intensity")
    security_row = next(row for row in rows if row["row_type"] == "security")
    assert security_row["method"] == "vacuum_weak_asymptotic"
    assert isinstance(security_row["warnings"], str)


def test_bb84_passes_surviving_photon_count_to_detector(monkeypatch) -> None:
    detector = RecordingDetector()
    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.source_from_config",
        lambda _config: TwoPhotonSource(),
    )
    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.channel_from_config",
        lambda _config: LosslessCountingChannel(),
    )
    monkeypatch.setattr(
        "qiskit_qkd.protocols.bb84.detector_from_config",
        lambda _config: detector,
    )
    scenario = Scenario(
        pulses=8,
        clock_rate_hz=1_000_000.0,
        seed=41,
        source=decoy_source_config(),
        store_full_event_log=True,
    )

    result = BB84Protocol().run(scenario, backend=EchoBackend())

    assert detector.signal_photon_numbers == [2] * scenario.pulses
    assert {event.surviving_photon_number for event in result.event_sample} == {2}


def test_vacuum_weak_decoy_estimator_bounds_single_photon_terms() -> None:
    scenario = Scenario(
        pulses=30_000,
        clock_rate_hz=1_000_000.0,
        seed=71,
        source=decoy_source_config(),
        post_processing=PostProcessingConfig(error_correction_efficiency=1.16),
    )
    decoy_rows = {
        "signal": {
            "pulses": 10_000,
            "mean_photon_number": 0.6,
            "selection_fraction": 1 / 3,
            "detected": 1_000,
            "sifted": 500,
            "errors": 5,
            "gain": 0.1,
            "qber": 0.01,
        },
        "decoy": {
            "pulses": 10_000,
            "mean_photon_number": 0.2,
            "selection_fraction": 1 / 3,
            "detected": 400,
            "sifted": 200,
            "errors": 4,
            "gain": 0.04,
            "qber": 0.02,
        },
        "vacuum": {
            "pulses": 10_000,
            "mean_photon_number": 0.0,
            "selection_fraction": 1 / 3,
            "detected": 10,
            "sifted": 5,
            "errors": 2,
            "gain": 0.001,
            "qber": 0.4,
        },
    }

    estimate = estimate_vacuum_weak_decoy_security(scenario, decoy_rows)

    assert estimate["valid"] is True
    assert estimate["signal_intensity"] == "signal"
    assert estimate["decoy_intensity"] == "decoy"
    assert estimate["vacuum_intensity"] == "vacuum"
    assert estimate["single_photon_yield_lower_bound"] == pytest.approx(
        0.2078,
        rel=1e-3,
    )
    assert estimate["single_photon_error_rate_upper_bound"] == pytest.approx(
        0.0115,
        rel=1e-2,
    )
    assert estimate["single_photon_gain_lower_bound"] > 0.06
    assert estimate["secret_key_rate_bps"] > 0.0


def test_vacuum_weak_decoy_estimator_zero_rate_for_worst_case_error() -> None:
    scenario = Scenario(
        pulses=30_000,
        clock_rate_hz=1_000_000.0,
        seed=73,
        source=decoy_source_config(),
        post_processing=PostProcessingConfig(error_correction_efficiency=1.0),
    )
    decoy_rows = {
        "signal": {
            "pulses": 21_000,
            "mean_photon_number": 0.6,
            "selection_fraction": 0.7,
            "detected": 100,
            "sifted": 50,
            "errors": 0,
            "gain": 0.001,
            "qber": 0.0,
        },
        "decoy": {
            "pulses": 6_000,
            "mean_photon_number": 0.2,
            "selection_fraction": 0.2,
            "detected": 1_800,
            "sifted": 900,
            "errors": 900,
            "gain": 0.3,
            "qber": 1.0,
        },
        "vacuum": {
            "pulses": 3_000,
            "mean_photon_number": 0.0,
            "selection_fraction": 0.1,
            "detected": 0,
            "sifted": 0,
            "errors": 0,
            "gain": 0.0,
            "qber": 0.0,
        },
    }

    estimate = estimate_vacuum_weak_decoy_security(scenario, decoy_rows)

    assert estimate["valid"] is True
    assert estimate["single_photon_error_rate_upper_bound"] == 1.0
    assert estimate["secret_fraction_per_signal_pulse"] == 0.0
    assert estimate["secret_key_rate_bps"] == 0.0
