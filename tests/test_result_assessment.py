from __future__ import annotations

import json

import pytest

from qiskit_qkd import (
    DecoyIntensity,
    E91Config,
    Metrics,
    PostProcessingConfig,
    ProtocolConfig,
    ResultAssessment,
    Scenario,
    SimulationResult,
    SourceConfig,
)
from qiskit_qkd.postprocessing import (
    estimate_vacuum_weak_decoy_security,
    qber,
    run_bb84_classical_postprocessing,
)


def test_zero_sifted_sample_has_no_qber_or_vacuous_verification() -> None:
    classical = run_bb84_classical_postprocessing(
        alice_bits=(),
        bob_bits=(),
        seed=7,
        config=PostProcessingConfig(),
    )
    result = SimulationResult(
        scenario=Scenario(pulses=16, clock_rate_hz=1_000.0, seed=7),
        metrics=Metrics(pulses=16),
        classical=classical.to_dict(),
    )

    assert qber(0, 0) is None
    assert classical.estimated_qber is None
    assert classical.qber_method == "unavailable"
    assert classical.verification_passed is False
    assert classical.verification_status == "not_applicable"
    assert result.metrics.qber == 0.0  # Legacy schema-v1 projection.
    assert result.assessment is not None
    assert result.assessment.data_status == "insufficient_data"
    assert result.assessment.qber_defined is False
    assert result.assessment.qber_value is None
    assert result.assessment.key_status == "no_key_insufficient_data"
    assert "NO_SIFTED_BITS" in result.assessment.reason_codes
    assert result.assessment.reasons


def test_fully_revealed_candidate_does_not_pass_verification_vacuously() -> None:
    classical = run_bb84_classical_postprocessing(
        alice_bits=(0, 1, 0, 1),
        bob_bits=(0, 1, 0, 1),
        seed=11,
        config=PostProcessingConfig(qber_sample_fraction=1.0),
    )

    assert classical.estimated_qber == 0.0
    assert classical.candidate_key_length == 0
    assert classical.verification_passed is False
    assert classical.verification_status == "not_applicable"


def test_failed_verification_marks_positive_legacy_rate_inconsistent() -> None:
    scenario = Scenario(pulses=100, clock_rate_hz=1_000.0, seed=13)
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(
            pulses=100,
            emitted=100,
            transmitted=100,
            detected=100,
            sifted=100,
            errors=2,
            qber=0.02,
            secret_key_rate_bps=717.1,
            abort=False,
        ),
        classical={
            "sifted_key_length": 100,
            "qber_sample_size": 0,
            "estimated_qber": 0.02,
            "qber_method": "full_sifted_key_diagnostic",
            "threshold": 0.11,
            "threshold_exceeded": False,
            "threshold_decision_source": "classical_estimate",
            "candidate_key_length": 100,
            "residual_mismatches": 2,
            "final_key_length": 0,
            "verification_passed": False,
            "verification_status": "failed",
        },
    )

    assert result.assessment is not None
    assert result.assessment.verification_status == "failed"
    assert result.assessment.key_status == "no_key_verification_failed"
    assert result.assessment.rate_estimate_status == "inconsistent_with_key_status"
    assert result.assessment.rate_estimate_bps == 717.1
    assert "LEGACY_RATE_INCONSISTENT_WITH_KEY_STATUS" in (
        result.assessment.reason_codes
    )


def test_schema_v1_payload_without_assessment_is_autoderived() -> None:
    original = SimulationResult(
        scenario=Scenario(pulses=10, clock_rate_hz=1_000.0, seed=17),
        metrics=Metrics(pulses=10),
    ).to_legacy_dict()

    restored = SimulationResult.from_dict(original)

    assert restored.assessment is not None
    assert restored.assessment.data_status == "insufficient_data"
    assert restored.to_dict()["schema_version"] == 2
    assert restored.to_dict()["assessment"]["qber_defined"] is False
    assert "assessment" not in restored.to_legacy_dict()


def test_classical_qber_sample_wins_over_legacy_metrics_and_records_mismatch() -> None:
    scenario = Scenario(
        pulses=100,
        clock_rate_hz=1_000.0,
        seed=18,
        post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
    )
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(
            pulses=100,
            emitted=100,
            transmitted=100,
            detected=100,
            sifted=100,
            errors=10,
            qber=0.10,
            abort=False,
        ),
        classical={
            "qber_sample_size": 10,
            "estimated_qber": 0.2,
            "qber_method": "revealed_sample",
            "threshold": 0.11,
            "threshold_exceeded": True,
            "threshold_decision_source": "classical_estimate",
            "abort": True,
            "final_key_length": 0,
            "verification_status": "not_performed",
        },
    )

    assert result.assessment.threshold_exceeded is True
    assert result.assessment.threshold_decision_source == "classical_estimate"
    assert result.assessment.qber_value == 0.2
    assert result.assessment.sample_size == 10
    assert "METRICS_CLASSICAL_ABORT_MISMATCH" in result.assessment.reason_codes


def test_scenario_threshold_is_authoritative_over_stored_classical_value() -> None:
    scenario = Scenario(
        pulses=10,
        clock_rate_hz=1_000.0,
        seed=181,
        post_processing=PostProcessingConfig(qber_abort_threshold=0.11),
    )
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(
            pulses=10,
            emitted=10,
            transmitted=10,
            detected=10,
            sifted=10,
            errors=2,
            qber=0.2,
            abort=True,
        ),
        classical={
            "qber_method": "full_sifted_key_diagnostic",
            "estimated_qber": 0.2,
            "qber_sample_size": 0,
            "threshold": 0.5,
            "threshold_exceeded": False,
        },
    )

    assert result.assessment.threshold == 0.11
    assert result.assessment.threshold_exceeded is True
    assert "CLASSICAL_THRESHOLD_CONFIG_MISMATCH" in result.assessment.reason_codes
    assert "CLASSICAL_THRESHOLD_EVIDENCE_MISMATCH" in result.assessment.reason_codes


def test_e91_without_chsh_sample_has_no_bell_conclusion() -> None:
    scenario = Scenario(
        pulses=16,
        clock_rate_hz=1_000.0,
        seed=19,
        protocol=ProtocolConfig(name="e91"),
        source=SourceConfig(kind="entangled_pair"),
        e91=E91Config(),
    )
    setting_rows = [
        {
            "setting_pair": f"A{alice}/B{bob}",
            "alice_setting": alice,
            "bob_setting": bob,
            "attempts": 4,
            "coincidences": 0,
            "same": 0,
            "different": 0,
            "used_for_chsh": True,
        }
        for alice, bob, _coefficient in scenario.e91.chsh_terms
    ]
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(pulses=16, chsh_s=None),
        bell={
            "chsh_s": None,
            "bell_violation": False,
            "setting_rows": setting_rows,
        },
    )

    assert result.assessment is not None
    assert result.assessment.observed_chsh_s is None
    assert result.assessment.chsh_sample_size == 0
    assert len(result.assessment.chsh_sample_size_by_term) == 4
    assert set(result.assessment.chsh_sample_size_by_term.values()) == {0}
    assert result.assessment.observed_threshold_exceeded is None
    assert (
        result.assessment.conclusion_scope
        == "diagnostic_fair_sampling_no_significance_test"
    )
    assert "CHSH_UNAVAILABLE" in result.assessment.reason_codes


def test_reserved_provenance_conflicts_are_preserved_but_not_authoritative() -> None:
    scenario = Scenario(pulses=8, clock_rate_hz=1_000.0, seed=23)
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(pulses=8),
        provenance={
            "schema_version": 999,
            "library_version": "legacy-build",
            "seed": 999,
            "scenario_digest": "not-the-scenario-digest",
            "rng": "spoofed-rng",
        },
        qiskit={"primitive": "test"},
    )

    assert result.provenance["schema_version"] == 2
    assert result.provenance["library_version"] != "legacy-build"
    assert result.provenance["seed"] == scenario.seed
    assert result.provenance["scenario_digest"] == scenario.digest()
    assert result.provenance["rng"] == "python.random.Random"
    conflicts = result.provenance["reserved_field_conflicts"]
    assert conflicts["seed"]["provided"] == 999
    assert conflicts["scenario_digest"]["provided"] == "not-the-scenario-digest"
    assert conflicts["rng"]["provided"] == "spoofed-rng"
    summary = result.summary()
    assert summary["assessment"] == result.assessment.to_dict()
    assert summary["provenance"] == result.provenance
    assert summary["qiskit"] == {"primitive": "test"}

    restored = SimulationResult.from_dict(result.to_dict())
    assert restored.provenance["reserved_field_conflicts"] == conflicts
    assert restored.assessment.to_dict() == result.assessment.to_dict()


def test_simulation_result_preserves_legacy_positional_signature() -> None:
    scenario = Scenario(pulses=8, clock_rate_hz=1_000.0, seed=24)
    metrics = Metrics(pulses=8)

    result = SimulationResult(
        scenario,
        metrics,
        {"backend": "legacy-positional"},
        {"primitive": "legacy-positional"},
        {},
        {},
        {},
        "producer-version",
        (),
        True,
    )

    assert result.library_version == "producer-version"
    assert result.provenance["backend"] == "legacy-positional"
    assert result.qiskit["primitive"] == "legacy-positional"
    assert result.assessment.qber_defined is False


def test_decoy_estimate_rejects_required_qber_without_a_sample() -> None:
    scenario = Scenario(
        pulses=30_000,
        clock_rate_hz=1_000_000.0,
        seed=29,
        source=SourceConfig(
            kind="decoy_weak_coherent",
            decoy_intensities=(
                DecoyIntensity("signal", 0.6, 0.7),
                DecoyIntensity("decoy", 0.2, 0.2),
                DecoyIntensity("vacuum", 0.0, 0.1),
            ),
        ),
    )
    rows = {
        "signal": {
            "pulses": 21_000,
            "selection_fraction": 0.7,
            "detected": 100,
            "sifted": 0,
            "errors": 0,
            "gain": 0.001,
            "qber": 0.0,
            "qber_defined": False,
        },
        "decoy": {
            "pulses": 6_000,
            "selection_fraction": 0.2,
            "detected": 100,
            "sifted": 50,
            "errors": 1,
            "gain": 0.01,
            "qber": 0.02,
            "qber_defined": True,
        },
        "vacuum": {
            "pulses": 3_000,
            "selection_fraction": 0.1,
            "detected": 0,
            "sifted": 0,
            "errors": 0,
            "gain": 0.0,
            "qber": 0.0,
            "qber_defined": False,
        },
    }

    estimate = estimate_vacuum_weak_decoy_security(scenario, rows)

    assert estimate["valid"] is False
    assert estimate["data_status"] == "insufficient_data"
    assert estimate["secret_key_rate_bps"] == 0.0
    assert "SIGNAL_QBER_UNAVAILABLE" in estimate["reason_codes"]


def test_result_writer_uses_v2_and_exports_a_real_v1_envelope() -> None:
    result = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=31),
        metrics=Metrics(pulses=8),
    )

    current = result.to_dict()
    legacy = result.to_legacy_dict()

    assert current["schema_version"] == 2
    assert current["provenance"]["schema_version"] == 2
    assert isinstance(current["assessment"], dict)
    assert legacy["schema_version"] == 1
    assert legacy["provenance"]["schema_version"] == 1
    assert "assessment" not in legacy
    assert set(legacy) == {
        "schema_version",
        "library_version",
        "scenario",
        "metrics",
        "provenance",
        "qiskit",
        "classical",
        "decoy",
        "bell",
        "event_sample",
        "aggregated",
    }
    assert "assessment" not in json.loads(result.to_legacy_json())

    restored = SimulationResult.from_dict(legacy)
    assert restored.assessment.qber_defined is False
    assert (
        restored.provenance["archive_load"]["assessment_source"]
        == "derived_from_schema_v1_missing_field"
    )
    assert restored.to_dict()["schema_version"] == 2


def test_v2_distinguishes_missing_and_null_assessment() -> None:
    payload = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=32),
        metrics=Metrics(pulses=8),
    ).to_dict()
    missing = dict(payload)
    missing.pop("assessment")
    explicit_null = dict(payload)
    explicit_null["assessment"] = None

    with pytest.raises(ValueError, match="requires an assessment field"):
        SimulationResult.from_dict(missing)
    with pytest.raises(ValueError, match="must not be null"):
        SimulationResult.from_dict(explicit_null)


@pytest.mark.parametrize("schema_version", [True, False, 1.0, 2.0, "2"])
def test_result_schema_version_rejects_bool_float_and_string(
    schema_version: object,
) -> None:
    payload = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=33),
        metrics=Metrics(pulses=8),
    ).to_dict()
    payload["schema_version"] = schema_version

    with pytest.raises(TypeError, match="schema_version must be an integer"):
        SimulationResult.from_dict(payload)


def test_archived_load_preserves_producer_without_current_model_backfill() -> None:
    payload = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=34),
        metrics=Metrics(pulses=8),
    ).to_legacy_dict()
    payload["library_version"] = "0.3.0"
    payload["provenance"] = {
        "library_version": "0.3.0",
        "producer": {"name": "historical-runner"},
    }

    restored = SimulationResult.from_dict(payload)

    assert restored.library_version == "0.3.0"
    assert restored.provenance["library_version"] == "0.3.0"
    assert restored.provenance["producer"] == {"name": "historical-runner"}
    assert "effective_model" not in restored.provenance
    audit = restored.provenance["archive_load"]
    assert audit["source_schema_version"] == 1
    assert audit["inferred_fields"]["seed"] == "serialized scenario"
    assert "effective_model" in audit["unavailable_fields"]


def test_archived_load_uses_unknown_instead_of_current_library_version() -> None:
    payload = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=35),
        metrics=Metrics(pulses=8),
    ).to_legacy_dict()
    payload.pop("library_version")
    payload["provenance"] = {}

    restored = SimulationResult.from_dict(payload)

    assert restored.library_version == "unknown"
    assert "library_version" not in restored.provenance
    assert "effective_model" not in restored.provenance


def test_archived_load_preserves_conflicting_producer_evidence_for_audit() -> None:
    scenario = Scenario(pulses=8, clock_rate_hz=1_000.0, seed=351)
    payload = SimulationResult(
        scenario=scenario,
        metrics=Metrics(pulses=8),
    ).to_legacy_dict()
    payload["provenance"] = {
        "schema_version": 77,
        "library_version": "producer-build",
        "seed": 999,
        "scenario_digest": "producer-digest",
        "effective_model": {"producer_model": True},
    }
    payload["library_version"] = "envelope-build"

    restored = SimulationResult.from_dict(payload)

    assert restored.provenance["schema_version"] == 77
    assert restored.provenance["library_version"] == "producer-build"
    assert restored.provenance["seed"] == 999
    assert restored.provenance["scenario_digest"] == "producer-digest"
    assert restored.provenance["effective_model"] == {"producer_model": True}
    conflicts = restored.provenance["archive_load"]["evidence_conflicts"]
    assert conflicts["schema_version"]["envelope_value"] == 1
    assert conflicts["seed"]["scenario_value"] == scenario.seed
    assert conflicts["scenario_digest"]["scenario_value"] == scenario.digest()
    assert conflicts["library_version"]["envelope_value"] == "envelope-build"


def test_supplied_assessment_is_checked_against_result_evidence() -> None:
    payload = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=36),
        metrics=Metrics(pulses=8),
    ).to_dict()
    payload["assessment"]["assumptions"].append("fabricated assumption")

    with pytest.raises(ValueError, match="disagrees.*assumptions"):
        SimulationResult.from_dict(payload)


def test_serialized_result_and_summary_are_deep_copies() -> None:
    result = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=37),
        metrics=Metrics(pulses=8),
        provenance={"custom": {"values": [1]}},
        qiskit={"nested": {"values": [2]}},
        classical={"nested": {"values": [3]}},
    )

    payload = result.to_dict()
    payload["provenance"]["custom"]["values"].append(9)
    payload["qiskit"]["nested"]["values"].append(9)
    payload["classical"]["nested"]["values"].append(9)
    payload["assessment"]["assumptions"].append("mutated")
    summary = result.summary()
    summary["provenance"]["custom"]["values"].append(8)

    assert result.provenance["custom"]["values"] == [1]
    assert result.qiskit["nested"]["values"] == [2]
    assert result.classical["nested"]["values"] == [3]
    assert "mutated" not in result.assessment.assumptions
    result.provenance["seed"] = 999
    result.qiskit["nested"]["values"].append(999)
    assert result.provenance["seed"] == result.scenario.seed
    assert result.qiskit["nested"]["values"] == [2]


def test_result_from_dict_requires_json_arrays() -> None:
    payload = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=38),
        metrics=Metrics(pulses=8),
    ).to_dict()
    payload["event_sample"] = ()
    with pytest.raises(TypeError, match="event_sample must be a JSON array"):
        SimulationResult.from_dict(payload)

    payload = SimulationResult(
        scenario=Scenario(pulses=8, clock_rate_hz=1_000.0, seed=39),
        metrics=Metrics(pulses=8),
    ).to_dict()
    payload["assessment"]["assumptions"] = tuple(
        payload["assessment"]["assumptions"],
    )
    with pytest.raises(TypeError, match="assumptions must be a JSON array"):
        SimulationResult.from_dict(payload)


def test_assessment_rejects_impossible_threshold_rate_and_chsh_states() -> None:
    result = SimulationResult(
        scenario=Scenario(pulses=10, clock_rate_hz=1_000.0, seed=40),
        metrics=Metrics(
            pulses=10,
            emitted=10,
            transmitted=10,
            detected=10,
            sifted=10,
            errors=2,
            qber=0.2,
            secret_key_rate_bps=5.0,
            abort=True,
        ),
    )
    threshold_payload = result.assessment.to_dict()
    threshold_payload["threshold_exceeded"] = False
    with pytest.raises(ValueError, match="qber_value > threshold"):
        ResultAssessment.from_dict(threshold_payload)

    rate_payload = result.assessment.to_dict()
    rate_payload["rate_estimate_status"] = "unavailable"
    with pytest.raises(ValueError, match="must not carry rate_estimate_bps"):
        ResultAssessment.from_dict(rate_payload)

    chsh_payload = result.assessment.to_dict()
    chsh_payload.update(
        {
            "observed_chsh_s": 2.5,
            "chsh_sample_size": 4,
            "chsh_sample_size_by_term": {"A0/B0": 4},
            "observed_threshold_exceeded": True,
            "conclusion_scope": "diagnostic_fair_sampling_no_significance_test",
        },
    )
    with pytest.raises(ValueError, match="only valid for E91"):
        ResultAssessment.from_dict(chsh_payload)

    with pytest.raises(ValueError, match="metrics.chsh_s is only valid"):
        SimulationResult(
            scenario=Scenario(pulses=1, clock_rate_hz=1_000.0, seed=401),
            metrics=Metrics(pulses=1, chsh_s=2.5),
        )


def test_e91_chsh_is_recomputed_from_term_counts_and_mismatches_are_audited() -> None:
    scenario = Scenario(
        pulses=4,
        clock_rate_hz=1_000.0,
        seed=41,
        protocol=ProtocolConfig(name="e91"),
        source=SourceConfig(kind="entangled_pair"),
    )
    rows = []
    for alice, bob, coefficient in scenario.e91.chsh_terms:
        rows.append(
            {
                "setting_pair": f"A{alice}/B{bob}",
                "alice_setting": alice,
                "bob_setting": bob,
                "used_for_chsh": True,
                "coincidences": 1,
                "same": int(coefficient == 1),
                "different": int(coefficient == -1),
            },
        )
    result = SimulationResult(
        scenario=scenario,
        metrics=Metrics(
            pulses=4,
            emitted=4,
            transmitted=4,
            detected=4,
            sifted=1,
            errors=0,
            qber=0.0,
            chsh_s=0.0,
        ),
        bell={
            "chsh_s": 0.0,
            "observed_chsh_s": 0.0,
            "setting_rows": rows,
        },
    )

    assert result.assessment.observed_chsh_s == 4.0
    assert result.assessment.observed_threshold_exceeded is True
    assert "BELL_CHSH_EVIDENCE_MISMATCH" in result.assessment.reason_codes
    assert "METRICS_CHSH_EVIDENCE_MISMATCH" in result.assessment.reason_codes

    serialized_assessment = result.assessment.to_dict()
    serialized_assessment["chsh_sample_size_by_term"]["A0/B0"] = 99
    assert result.assessment.chsh_sample_size_by_term["A0/B0"] == 1
    result.assessment.chsh_sample_size_by_term["A0/B0"] = 99
    assert result.assessment.chsh_sample_size_by_term["A0/B0"] == 1

    missing_scope = result.assessment.to_dict()
    missing_scope["conclusion_scope"] = None
    with pytest.raises(ValueError, match="E91 assessments require"):
        ResultAssessment.from_dict(missing_scope)

    invalid_rows = [dict(row) for row in rows]
    invalid_rows[0]["same"] = 2
    with pytest.raises(ValueError, match=r"same\+different exceeds"):
        SimulationResult(
            scenario=scenario,
            metrics=Metrics(
                pulses=4,
                emitted=4,
                transmitted=4,
                detected=4,
                sifted=1,
                errors=0,
                qber=0.0,
                chsh_s=4.0,
            ),
            bell={"chsh_s": 4.0, "setting_rows": invalid_rows},
        )
