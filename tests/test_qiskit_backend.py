import math

import pytest
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

from qiskit_qkd import ChannelConfig, Scenario, SimulationResult
from qiskit_qkd.backends import QiskitSamplerBackend, backend_from_scenario
from qiskit_qkd.protocols import BB84Protocol
from qiskit_qkd.qiskit_integration import CircuitFactory


@pytest.mark.parametrize(
    ("bit", "basis"),
    [
        (0, "Z"),
        (1, "Z"),
        (0, "X"),
        (1, "X"),
    ],
)
def test_qiskit_sampler_backend_preserves_bits_for_matching_bases(
    bit: int,
    basis: str,
) -> None:
    backend = QiskitSamplerBackend(seed=17)

    assert backend.measure_bb84(bit, basis, basis) == bit


def test_qiskit_sampler_backend_records_circuits_and_counts() -> None:
    backend = QiskitSamplerBackend(seed=17)

    measured = backend.measure_bb84(1, "X", "X")

    assert measured == 1
    assert len(backend.last_circuits) == 1
    assert isinstance(backend.last_circuits[0], QuantumCircuit)
    assert backend.last_circuits[0].metadata["protocol"] == "BB84"
    assert backend.last_counts == [{"1": 1}]


def test_noiseless_bb84_statevector_sampling_uses_probabilities_with_seed() -> None:
    backend = QiskitSamplerBackend(
        seed=17,
        max_recorded_results=0,
        channel_rotation_y_rad=math.pi / 4,
    )

    bits = backend.measure_bb84_batch([(0, "Z", "Z")] * 400)

    ones = sum(bits)
    assert 0 < ones < 120


def test_external_sampler_counts_are_sampled_not_majority_voted() -> None:
    backend = QiskitSamplerBackend(
        sampler=StatevectorSampler(seed=17),
        seed=17,
        shots_per_circuit=1024,
        max_recorded_results=0,
    )

    bits = backend.measure_bb84_batch([(0, "Z", "X")] * 400)

    ones = sum(bits)
    assert 150 <= ones <= 250


def test_qiskit_sampler_backend_limits_recorded_execution_artifacts() -> None:
    backend = QiskitSamplerBackend(seed=17, max_recorded_results=2)

    bits = backend.measure_bb84_batch(
        [
            (0, "Z", "Z"),
            (1, "Z", "Z"),
            (0, "X", "X"),
            (1, "X", "X"),
            (0, "Z", "Z"),
        ],
    )

    summary = backend.qiskit_summary()
    assert bits == (0, 1, 0, 1, 0)
    assert summary["circuit_count"] == 5
    assert len(backend.last_circuits) == 2
    assert len(backend.last_counts) == 2
    assert summary["counts_sample"] == [{"0": 1}, {"1": 1}]
    assert sum(summary["counts_by_outcome"].values()) == 5


def test_bb84_result_exports_qiskit_execution_summary() -> None:
    scenario = Scenario(pulses=4, clock_rate_hz=1_000_000.0, seed=17)
    backend = QiskitSamplerBackend(seed=17)

    result = BB84Protocol().run(scenario, backend=backend)
    payload = result.to_dict()

    assert payload["qiskit"]["backend"] == "QiskitSamplerBackend"
    assert payload["qiskit"]["primitive"] == "StatevectorSampler"
    assert payload["qiskit"]["shots_per_circuit"] == 1
    assert payload["qiskit"]["circuit_count"] == scenario.pulses
    assert payload["qiskit"]["counts_sample"] == backend.last_counts
    assert payload["qiskit"]["circuit_metadata_sample"][0]["protocol"] == "BB84"
    assert "e91_noiseless_sampler" not in payload["qiskit"]
    assert SimulationResult.from_json(result.to_json()).qiskit == result.qiskit


def test_scenario_aer_noise_rejects_explicit_ideal_backend() -> None:
    scenario = Scenario(
        pulses=4,
        clock_rate_hz=1_000_000.0,
        seed=17,
        channel=ChannelConfig(depolarizing_probability=0.25),
    )

    with pytest.raises(ValueError, match="requires Qiskit Aer noise"):
        BB84Protocol().run(scenario, backend=QiskitSamplerBackend(seed=17))


def test_scenario_aer_noise_rejects_non_aer_explicit_sampler() -> None:
    scenario = Scenario(
        pulses=4,
        clock_rate_hz=1_000_000.0,
        seed=18,
        channel=ChannelConfig(depolarizing_probability=0.25),
    )
    backend = QiskitSamplerBackend(
        sampler=StatevectorSampler(seed=18),
        noise_model=object(),
    )

    with pytest.raises(ValueError, match="non-Aer sampler"):
        BB84Protocol().run(scenario, backend=backend)


def test_scenario_factory_rejects_noisy_backend_for_silent_scenario() -> None:
    class NoisyBackend:
        noise_model = object()

    scenario = Scenario(pulses=1, clock_rate_hz=1_000_000.0, seed=19)

    with pytest.raises(ValueError, match="has no Aer quantum/readout noise"):
        backend_from_scenario(scenario, backend=NoisyBackend())


def test_scenario_factory_rejects_reusing_backend_for_new_aer_signature() -> None:
    first = Scenario(
        pulses=2,
        clock_rate_hz=1_000_000.0,
        seed=23,
    )
    second = Scenario(
        pulses=2,
        clock_rate_hz=1_000_000.0,
        seed=23,
        channel=ChannelConfig(depolarizing_probability=0.25),
    )
    backend = QiskitSamplerBackend(seed=23)
    BB84Protocol().run(first, backend=backend)

    with pytest.raises(ValueError, match="requires Qiskit Aer noise"):
        BB84Protocol().run(second, backend=backend)


def test_configuring_backend_for_new_scenario_resets_execution_summary() -> None:
    backend = QiskitSamplerBackend(seed=17, max_recorded_results=0)
    protocol = BB84Protocol()
    first = Scenario(pulses=2, clock_rate_hz=1_000_000.0, seed=17)
    second = Scenario(pulses=3, clock_rate_hz=1_000_000.0, seed=18)

    first_result = protocol.run(first, backend=backend)
    second_result = protocol.run(second, backend=backend)

    assert first_result.qiskit["circuit_count"] == 2
    assert second_result.qiskit["circuit_count"] == 3
    assert sum(second_result.qiskit["counts_by_outcome"].values()) == 3
    assert second_result.qiskit["backend_initial_seed"] == 17
    assert second_result.qiskit["backend_seed"] == 18
    assert second_result.qiskit["effective_scenario_seed"] == 18
    assert second_result.qiskit["primitive_seed"] == 17
    assert second_result.qiskit["preparation_rng_seed"] == 18 + 0x51A7E
    assert second_result.qiskit["measurement_rng_seed"] == 18 + 0xE91


def test_statevector_cache_key_uses_circuit_not_incomplete_metadata(
    monkeypatch,
) -> None:
    original = CircuitFactory.bb84_prepare_measure

    def without_metadata(*args, **kwargs):
        circuit = original(*args, **kwargs)
        circuit.metadata = {}
        return circuit

    monkeypatch.setattr(
        "qiskit_qkd.backends.qiskit_sampler.CircuitFactory.bb84_prepare_measure",
        without_metadata,
    )
    backend = QiskitSamplerBackend(seed=31, max_recorded_results=0)

    bits = backend.measure_bb84_batch([(0, "Z", "Z"), (1, "Z", "Z")])

    assert bits == (0, 1)


def test_statevector_cache_handles_non_hashable_metadata_and_reports_hits(
    monkeypatch,
) -> None:
    original = CircuitFactory.bb84_prepare_measure

    def with_nested_metadata(*args, **kwargs):
        circuit = original(*args, **kwargs)
        circuit.metadata = {"nested": {"values": [1, 2, 3]}}
        return circuit

    monkeypatch.setattr(
        "qiskit_qkd.backends.qiskit_sampler.CircuitFactory.bb84_prepare_measure",
        with_nested_metadata,
    )
    backend = QiskitSamplerBackend(seed=37, max_recorded_results=0)

    backend.measure_bb84_batch([(0, "Z", "Z")] * 2)
    summary = backend.qiskit_summary()

    assert summary["statevector_cache_misses"] == 1
    assert summary["statevector_cache_hits"] == 1
    assert summary["statevector_cache_size"] == 1


def test_statevector_cache_is_bounded_and_reset_between_scenarios() -> None:
    backend = QiskitSamplerBackend(
        seed=41,
        max_recorded_results=0,
        max_statevector_cache_entries=2,
    )
    protocol = BB84Protocol()
    scenario = Scenario(pulses=8, clock_rate_hz=1_000_000.0, seed=41)

    first = protocol.run(scenario, backend=backend)
    second = protocol.run(scenario, backend=backend)

    assert first.qiskit["statevector_cache_size"] <= 2
    assert first.qiskit["statevector_cache_evictions"] > 0
    assert second.qiskit["statevector_cache_size"] <= 2
    assert second.qiskit["statevector_cache_misses"] > 0


def test_noiseless_grouping_preserves_rng_sequence_and_reuses_circuits(
    monkeypatch,
) -> None:
    original = CircuitFactory.bb84_prepare_measure
    calls = 0

    def counting_factory(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(
        "qiskit_qkd.backends.qiskit_sampler.CircuitFactory.bb84_prepare_measure",
        counting_factory,
    )
    states = ((0, "Z", "X"), (1, "Z", "X"), (0, "X", "Z"), (1, "X", "Z"))
    rounds = tuple(states[index % len(states)] for index in range(32))
    backend = QiskitSamplerBackend(
        seed=73,
        preparation_error_probability=0.25,
        max_recorded_results=0,
    )

    bits = backend.measure_bb84_batch(rounds)

    assert bits == (
        1,
        1,
        0,
        0,
        0,
        1,
        0,
        1,
        1,
        0,
        0,
        0,
        0,
        1,
        1,
        0,
        0,
        0,
        1,
        1,
        0,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        1,
        0,
        1,
    )
    assert backend._preparation_rng.random() == 0.9986087719250588
    assert backend._measurement_rng.random() == 0.06130370584573552
    assert calls <= 8
