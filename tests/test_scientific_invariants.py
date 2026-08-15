"""Cross-layer scientific invariants with explicit statistical tolerances."""

from __future__ import annotations

import math
import random
from dataclasses import replace

from qiskit_qkd import (
    ChannelConfig,
    DetectorConfig,
    E91Config,
    EveConfig,
    PostProcessingConfig,
    ProtocolConfig,
    QiskitSamplerBackend,
    Scenario,
    SimulationResult,
    SourceConfig,
)
from qiskit_qkd.protocols import BB84Protocol, E91Protocol

SIFTING_FRACTION_BOUNDS = (0.44, 0.56)
INTERCEPT_RESEND_QBER_BOUNDS = (0.20, 0.30)
EVE_INFORMATION_BOUNDS = (0.44, 0.56)
E91_CHSH_ABS_TOLERANCE = 0.40


class SeededIdealBB84Backend:
    """Fast projective-measurement boundary for physical-layer invariants."""

    max_circuits_per_job = 512

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def measure_bb84_batch(
        self,
        rounds: list[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        return tuple(
            bit if prepared_basis == measured_basis else self._rng.randrange(2)
            for bit, prepared_basis, measured_basis in rounds
        )

    def provenance(self) -> dict[str, object]:
        return {"backend": type(self).__name__}

    def qiskit_summary(self) -> dict[str, object]:
        return {"circuit_count": 0, "counts_sample": []}


def _bb84_scenario(*, seed: int, pulses: int = 2_048) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        source=SourceConfig(kind="ideal_single_photon", emission_probability=1.0),
        channel=ChannelConfig(kind="fiber", distance_km=0.0),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(
            qber_abort_threshold=None,
            qber_sample_fraction=0.0,
        ),
    )


def _run_bb84(scenario: Scenario) -> SimulationResult:
    return BB84Protocol().run(
        scenario,
        backend=SeededIdealBB84Backend(seed=scenario.seed + 10_000),
    )


def test_zero_detections_keep_legacy_zero_but_mark_qber_undefined() -> None:
    scenario = replace(
        _bb84_scenario(seed=101, pulses=256),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=0.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
    )

    result = _run_bb84(scenario)

    assert result.metrics.detected == 0
    assert result.metrics.sifted == 0
    assert result.metrics.qber == 0.0  # Stable schema-v1 placeholder.
    assert result.assessment is not None
    assert result.assessment.data_status == "insufficient_data"
    assert result.assessment.qber_defined is False
    assert result.assessment.qber_value is None
    assert result.assessment.sample_size == 0
    assert result.assessment.qber_method == "unavailable"
    assert result.assessment.key_status == "no_key_insufficient_data"
    assert result.assessment.rate_estimate_status == "unavailable"


def test_ideal_bb84_is_reproducible_and_respects_binomial_bounds() -> None:
    scenario = _bb84_scenario(seed=211)
    first = _run_bb84(scenario)
    repeated = _run_bb84(scenario)
    other_seed = _run_bb84(_bb84_scenario(seed=212))

    assert first.to_dict() == repeated.to_dict()
    assert first.provenance["effective_model"] == repeated.provenance[
        "effective_model"
    ]
    assert first.provenance["scenario_digest"] != other_seed.provenance[
        "scenario_digest"
    ]

    # For n=2048, +/-0.06 around p=0.5 is a deliberately loose (>6 sigma)
    # acceptance band. A different seed is required to stay physical, not to
    # produce a particular unequal counter value.
    for result in (first, other_seed):
        sifted_fraction = result.metrics.sifted / result.metrics.detected
        assert result.metrics.detected == result.scenario.pulses
        assert SIFTING_FRACTION_BOUNDS[0] <= sifted_fraction
        assert sifted_fraction <= SIFTING_FRACTION_BOUNDS[1]
        assert result.metrics.errors == 0
        assert result.metrics.qber == 0.0
        assert result.assessment is not None
        assert result.assessment.qber_defined is True
        assert result.assessment.qber_value == 0.0
        assert result.assessment.sample_size == result.metrics.sifted
        assert result.assessment.qber_method == "full_sifted_key_diagnostic"
        assert result.assessment.security_scope == (
            "pedagogical_asymptotic_diagnostic"
        )
        assert result.assessment.finite_key is False
        assert result.assessment.composable is False


def test_paired_seeds_preserve_loss_and_efficiency_monotonicity() -> None:
    # Common random numbers turn the probability comparisons into nested
    # events. This intentionally avoids claiming pointwise ordering for two
    # unrelated Monte Carlo samples.
    loss_base = _bb84_scenario(seed=307)
    zero_length = _run_bb84(loss_base)
    lossy = _run_bb84(
        replace(
            loss_base,
            channel=ChannelConfig(kind="fiber", distance_km=40.0),
        ),
    )

    assert zero_length.metrics.transmitted > lossy.metrics.transmitted
    assert zero_length.metrics.detected > lossy.metrics.detected
    assert zero_length.metrics.detected == zero_length.metrics.transmitted
    assert lossy.metrics.detected == lossy.metrics.transmitted

    efficiency_base = _bb84_scenario(seed=311)
    high_efficiency = _run_bb84(
        replace(
            efficiency_base,
            detector=replace(efficiency_base.detector, efficiency=0.85),
        ),
    )
    low_efficiency = _run_bb84(
        replace(
            efficiency_base,
            detector=replace(efficiency_base.detector, efficiency=0.25),
        ),
    )

    assert high_efficiency.metrics.transmitted == low_efficiency.metrics.transmitted
    assert high_efficiency.metrics.detected > low_efficiency.metrics.detected


def test_full_intercept_resend_has_expected_qber_and_eve_information() -> None:
    scenario = replace(
        _bb84_scenario(seed=401, pulses=4_096),
        eavesdropper=EveConfig(
            kind="intercept_resend",
            intercept_probability=1.0,
        ),
    )

    result = _run_bb84(scenario)

    assert result.metrics.eve_intercepted_fraction == 1.0
    assert INTERCEPT_RESEND_QBER_BOUNDS[0] <= result.metrics.qber
    assert result.metrics.qber <= INTERCEPT_RESEND_QBER_BOUNDS[1]
    assert EVE_INFORMATION_BOUNDS[0] <= result.metrics.eve_information_estimate
    assert result.metrics.eve_information_estimate <= EVE_INFORMATION_BOUNDS[1]
    assert result.assessment is not None
    assert result.assessment.qber_defined is True
    assert result.assessment.qber_value == result.classical["estimated_qber"]


def test_e91_reports_observed_chsh_with_sample_and_limited_conclusion() -> None:
    scenario = Scenario(
        pulses=1_024,
        clock_rate_hz=1_000_000.0,
        seed=509,
        protocol=ProtocolConfig(name="e91"),
        e91=E91Config(),
        source=SourceConfig(kind="entangled_pair", emission_probability=1.0),
        channel=ChannelConfig(kind="ideal"),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=1.0,
            dark_count_rate_hz=0.0,
            gate_width_s=1e-9,
        ),
        post_processing=PostProcessingConfig(qber_abort_threshold=None),
    )

    result = E91Protocol().run(
        scenario,
        backend=QiskitSamplerBackend(
            seed=scenario.seed,
            max_circuits_per_job=512,
            max_recorded_results=0,
        ),
    )

    assert result.assessment is not None
    assessment = result.assessment
    assert assessment.observed_chsh_s == result.metrics.chsh_s
    assert assessment.observed_chsh_s is not None
    # About 170 coincidences per term make +/-0.40 deliberately tolerant of
    # Monte Carlo variation while keeping the accepted ideal band above 2.
    assert math.isclose(
        assessment.observed_chsh_s,
        2.0 * math.sqrt(2.0),
        abs_tol=E91_CHSH_ABS_TOLERANCE,
    )
    assert assessment.chsh_sample_size == sum(
        assessment.chsh_sample_size_by_term.values()
    )
    assert len(assessment.chsh_sample_size_by_term) == 4
    assert all(size > 0 for size in assessment.chsh_sample_size_by_term.values())
    assert 0.55 * scenario.pulses <= assessment.chsh_sample_size
    assert assessment.chsh_sample_size <= 0.78 * scenario.pulses
    assert assessment.observed_threshold_exceeded is True
    assert assessment.conclusion_scope == (
        "diagnostic_fair_sampling_no_significance_test"
    )
    assert any("fair sampling" in item for item in assessment.assumptions)
    assert any("no statistical significance" in item for item in assessment.assumptions)
    assert any(
        "detection or locality loopholes" in item
        for item in assessment.assumptions
    )
    assert any("device-independent" in item for item in assessment.assumptions)
