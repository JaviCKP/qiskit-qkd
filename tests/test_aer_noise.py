from __future__ import annotations

import pytest

pytest.importorskip("qiskit_aer")

from qiskit_qkd import (
    ChannelConfig,
    DetectorConfig,
    E91Config,
    ProtocolConfig,
    Scenario,
    SourceConfig,
)
from qiskit_qkd.backends import QiskitSamplerBackend, backend_from_scenario
from qiskit_qkd.protocols import BB84Protocol, E91Protocol


def _aer_noise_adapter():
    import qiskit_qkd.qiskit_integration as integration

    assert hasattr(integration, "AerNoiseModelAdapter")
    return integration.AerNoiseModelAdapter


def _transpilation_options():
    import qiskit_qkd.qiskit_integration as integration

    assert hasattr(integration, "TranspilationOptions")
    return integration.TranspilationOptions


def test_aer_noise_adapter_translates_only_quantum_and_readout_noise() -> None:
    scenario = Scenario(
        pulses=1,
        clock_rate_hz=1_000_000.0,
        seed=7,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=80.0,
            attenuation_db_km=0.2,
            depolarizing_probability=0.12,
            phase_damping_probability=0.34,
        ),
        detector=DetectorConfig(readout_error_probability=0.08),
    )

    adapter = _aer_noise_adapter().from_scenario(scenario)
    summary = adapter.summary()

    assert summary["enabled"] is True
    assert summary["components"] == [
        "channel_depolarizing",
        "channel_phase_damping",
        "detector_readout",
    ]
    assert summary["quantum_error_operations"] == ["id"]
    assert summary["readout_error_operations"] == ["measure"]
    assert summary["event_layer_exclusions"] == [
        "fiber_loss_no_click",
        "detector_efficiency",
        "dark_counts",
        "dead_time",
        "afterpulsing",
        "timing_gates",
    ]


def test_aer_noise_adapter_does_not_encode_loss_as_noise_model() -> None:
    scenario = Scenario(
        pulses=1,
        clock_rate_hz=1_000_000.0,
        seed=7,
        channel=ChannelConfig(
            kind="fiber",
            distance_km=120.0,
            attenuation_db_km=0.2,
            fixed_loss_db=3.0,
        ),
    )

    adapter = _aer_noise_adapter().from_scenario(scenario)

    assert adapter.summary()["enabled"] is False
    assert adapter.summary()["components"] == []
    assert adapter.noise_model.to_dict()["errors"] == []


def test_readout_error_flips_a_trivial_bb84_measurement() -> None:
    scenario = Scenario(
        pulses=1,
        clock_rate_hz=1_000_000.0,
        seed=11,
        detector=DetectorConfig(readout_error_probability=1.0),
    )
    adapter = _aer_noise_adapter().from_scenario(scenario)
    backend = QiskitSamplerBackend(
        seed=11,
        seed_simulator=11,
        shots_per_circuit=25,
        noise_model=adapter.noise_model,
    )

    assert backend.measure_bb84(0, "Z", "Z") == 1
    assert backend.last_counts == [{"1": 25}]


def test_phase_damping_degrades_x_basis_more_than_z_basis() -> None:
    scenario = Scenario(
        pulses=1,
        clock_rate_hz=1_000_000.0,
        seed=13,
        channel=ChannelConfig(phase_damping_probability=1.0),
    )
    adapter = _aer_noise_adapter().from_scenario(scenario)
    backend = QiskitSamplerBackend(
        seed=13,
        seed_simulator=13,
        shots_per_circuit=400,
        noise_model=adapter.noise_model,
    )

    backend.measure_bb84_batch([(0, "Z", "Z"), (0, "X", "X")])
    z_counts, x_counts = backend.last_counts

    assert z_counts.get("1", 0) == 0
    assert 120 <= x_counts.get("1", 0) <= 280


def test_depolarizing_noise_increases_bb84_qber_without_classical_shortcuts() -> None:
    ideal = Scenario(pulses=300, clock_rate_hz=1_000_000.0, seed=19)
    noisy = Scenario(
        pulses=300,
        clock_rate_hz=1_000_000.0,
        seed=19,
        channel=ChannelConfig(depolarizing_probability=1.0),
    )

    ideal_result = BB84Protocol().run(
        ideal,
        backend=QiskitSamplerBackend(seed=19, seed_simulator=19),
    )
    noisy_adapter = _aer_noise_adapter().from_scenario(noisy)
    noisy_result = BB84Protocol().run(
        noisy,
        backend=QiskitSamplerBackend(
            seed=19,
            seed_simulator=19,
            noise_model=noisy_adapter.noise_model,
        ),
    )

    assert ideal_result.metrics.qber == 0.0
    assert noisy_result.metrics.qber > ideal_result.metrics.qber
    assert noisy_result.metrics.qber >= 0.15
    assert noisy_result.classical["sifted_key_length"] == noisy_result.metrics.sifted


def test_bb84_protocol_auto_applies_aer_noise_from_scenario() -> None:
    noisy = Scenario(
        pulses=300,
        clock_rate_hz=1_000_000.0,
        seed=21,
        channel=ChannelConfig(depolarizing_probability=1.0),
    )

    result = BB84Protocol().run(noisy)

    assert result.metrics.qber >= 0.15
    assert result.qiskit["noise_model"]["enabled"] is True
    assert result.qiskit["noise_model"]["components"] == ["channel_depolarizing"]


def test_scenario_factory_rejects_reusing_noisy_backend_for_new_noise_values() -> None:
    first = Scenario(
        pulses=2,
        clock_rate_hz=1_000_000.0,
        seed=21,
        channel=ChannelConfig(depolarizing_probability=0.1),
    )
    second = Scenario(
        pulses=2,
        clock_rate_hz=1_000_000.0,
        seed=21,
        channel=ChannelConfig(depolarizing_probability=0.2),
    )
    backend = backend_from_scenario(first)

    with pytest.raises(ValueError, match="different scenario Aer-noise signature"):
        backend_from_scenario(second, backend=backend)


def test_bb84_protocol_auto_applies_readout_error_from_scenario() -> None:
    scenario = Scenario(
        pulses=64,
        clock_rate_hz=1_000_000.0,
        seed=22,
        detector=DetectorConfig(readout_error_probability=1.0),
    )

    result = BB84Protocol().run(scenario)

    assert result.metrics.qber == 1.0
    assert result.qiskit["noise_model"]["components"] == ["detector_readout"]


def test_e91_detector_readout_overrides_are_applied_to_each_qubit() -> None:
    scenario = Scenario(
        pulses=1,
        clock_rate_hz=1_000_000.0,
        seed=23,
        protocol=ProtocolConfig(name="e91"),
        source=SourceConfig(kind="entangled_pair", emission_probability=1.0),
        channel=ChannelConfig(kind="ideal"),
        detector=DetectorConfig(kind="threshold", efficiency=1.0),
        e91=E91Config(
            alice_detector=DetectorConfig(
                kind="threshold",
                efficiency=1.0,
                readout_error_probability=1.0,
            ),
            bob_detector=DetectorConfig(kind="threshold", efficiency=1.0),
        ),
    )
    adapter = _aer_noise_adapter().from_scenario(scenario)
    summary = adapter.summary()

    assert summary["parameters"]["alice_readout_error_probability"] == 1.0
    assert summary["parameters"]["bob_readout_error_probability"] == 0.0
    assert summary["parameters"]["readout_error_qubits"] == {"alice": [0]}
    assert [
        error["gate_qubits"]
        for error in adapter.noise_model.to_dict()["errors"]
        if error["type"] == "roerror"
    ] == [[(0,)]]

    backend = QiskitSamplerBackend(
        seed=23,
        seed_simulator=23,
        shots_per_circuit=256,
        noise_model=adapter.noise_model,
    )
    backend.measure_e91_batch([(0.0, 0.0, "psi_minus")])
    # The ideal singlet is anti-correlated in Z.  Flipping only Alice makes
    # all sampled readouts correlated; Bob's qubit remains untouched.
    counts = backend.last_counts[0]
    assert set(counts) <= {"00", "11"}


def test_e91_protocol_auto_applies_asymmetric_readout_noise() -> None:
    scenario = Scenario(
        pulses=64,
        clock_rate_hz=1_000_000.0,
        seed=24,
        protocol=ProtocolConfig(name="e91"),
        source=SourceConfig(kind="entangled_pair", emission_probability=1.0),
        channel=ChannelConfig(kind="ideal"),
        detector=DetectorConfig(kind="threshold", efficiency=1.0),
        e91=E91Config(
            alice_detector=DetectorConfig(
                kind="threshold",
                efficiency=1.0,
                readout_error_probability=1.0,
            ),
            bob_detector=DetectorConfig(kind="threshold", efficiency=1.0),
        ),
    )

    result = E91Protocol().run(scenario)

    assert result.provenance["alice_readout_error_probability"] == 1.0
    assert result.provenance["bob_readout_error_probability"] == 0.0
    diagnostics = result.qiskit["e91_effective_diagnostics"]
    assert diagnostics["detector_readout_error_probabilities"] == {
        "alice": 1.0,
        "bob": 0.0,
    }


def test_transpilation_options_preserve_metadata_and_are_reported() -> None:
    transpilation = _transpilation_options()(optimization_level=1, seed_transpiler=23)
    backend = QiskitSamplerBackend(seed=23, transpilation=transpilation)

    assert backend.measure_bb84(1, "X", "X") == 1
    summary = backend.qiskit_summary()

    assert backend.last_circuits[0].metadata["protocol"] == "BB84"
    assert summary["transpilation"] == {
        "enabled": True,
        "optimization_level": 1,
        "seed_transpiler": 23,
        "basis_gates": None,
        "backend": None,
        "target": None,
    }


def test_qiskit_summary_records_aer_versions_noise_and_seeds() -> None:
    scenario = Scenario(
        pulses=2,
        clock_rate_hz=1_000_000.0,
        seed=29,
        channel=ChannelConfig(depolarizing_probability=0.25),
    )
    adapter = _aer_noise_adapter().from_scenario(scenario)
    backend = QiskitSamplerBackend(
        seed=29,
        seed_simulator=31,
        noise_model=adapter.noise_model,
        noise_summary=adapter.summary(),
        transpilation=_transpilation_options()(
            optimization_level=0,
            seed_transpiler=37,
        ),
    )

    result = BB84Protocol().run(scenario, backend=backend)
    summary = result.qiskit

    assert summary["qiskit_aer_version"] is not None
    assert summary["seed_simulator"] == 31
    assert summary["backend_seed"] == 29
    assert summary["noise_model"]["components"] == ["channel_depolarizing"]
    assert summary["transpilation"]["seed_transpiler"] == 37


def test_transpilation_preserves_aer_channel_noise_marker() -> None:
    scenario = Scenario(
        pulses=300,
        clock_rate_hz=1_000_000.0,
        seed=41,
        channel=ChannelConfig(depolarizing_probability=1.0),
    )
    adapter = _aer_noise_adapter().from_scenario(scenario)
    backend = QiskitSamplerBackend(
        seed=41,
        seed_simulator=41,
        max_recorded_results=1,
        noise_model=adapter.noise_model,
        noise_summary=adapter.summary(),
        transpilation=_transpilation_options()(
            optimization_level=1,
            seed_transpiler=41,
        ),
    )

    result = BB84Protocol().run(scenario, backend=backend)

    assert result.metrics.qber >= 0.15
    assert backend.last_circuits[0].count_ops()["id"] == 1
    assert result.qiskit["transpilation"]["optimization_level"] == 0
    assert result.qiskit["transpilation"]["requested_optimization_level"] == 1
