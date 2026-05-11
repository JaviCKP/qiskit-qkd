from qiskit_qkd import PostProcessingConfig, Scenario, SimulationResult
from qiskit_qkd.backends import QiskitSamplerBackend
from qiskit_qkd.protocols import BB84Protocol


class BatchOnlyBackend:
    def __init__(self) -> None:
        self.batches: list[tuple[tuple[int, str, str], ...]] = []

    def measure_bb84(self, bit: int, alice_basis: str, bob_basis: str) -> int:
        raise AssertionError("BB84Protocol should use batched backend execution")

    def measure_bb84_batch(
        self,
        rounds: list[tuple[int, str, str]],
    ) -> tuple[int, ...]:
        batch = tuple(rounds)
        self.batches.append(batch)
        return tuple(
            bit if alice_basis == bob_basis else 0
            for bit, alice_basis, bob_basis in batch
        )

    def provenance(self) -> dict[str, object]:
        return {"backend": "BatchOnlyBackend"}

    def qiskit_summary(self) -> dict[str, object]:
        return {"circuit_count": 0, "counts_sample": []}


def build_scenario(
    *,
    pulses: int = 512,
    seed: int = 123,
    event_sample_size: int = 0,
) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        post_processing=PostProcessingConfig(
            qber_abort_threshold=0.11,
            error_correction_efficiency=1.16,
        ),
        event_sample_size=event_sample_size,
    )


def test_bb84_ideal_run_returns_result_with_zero_qber() -> None:
    scenario = build_scenario(pulses=128, seed=7)
    result = BB84Protocol().run(scenario, backend=QiskitSamplerBackend(seed=7))

    assert isinstance(result, SimulationResult)
    assert result.metrics.qber == 0.0
    assert result.metrics.errors == 0
    assert result.metrics.abort is False


def test_bb84_ideal_sifted_fraction_is_close_to_half() -> None:
    scenario = build_scenario(pulses=512, seed=11)
    result = BB84Protocol().run(scenario, backend=QiskitSamplerBackend(seed=11))

    assert result.metrics.detected == scenario.pulses
    assert abs(result.metrics.sifted / result.metrics.detected - 0.5) <= 0.08


def test_bb84_same_seed_produces_same_summary() -> None:
    scenario = build_scenario(pulses=128, seed=19, event_sample_size=8)

    first = BB84Protocol().run(scenario, backend=QiskitSamplerBackend(seed=19))
    second = BB84Protocol().run(scenario, backend=QiskitSamplerBackend(seed=19))

    assert first.summary() == second.summary()


def test_bb84_event_sample_size_is_respected() -> None:
    scenario = build_scenario(pulses=32, seed=23, event_sample_size=5)
    result = BB84Protocol().run(scenario, backend=QiskitSamplerBackend(seed=23))

    assert len(result.event_sample) == 5
    assert result.summary()["event_sample_size"] == 5


def test_bb84_uses_batched_backend_without_full_event_log() -> None:
    scenario = build_scenario(pulses=16, seed=29, event_sample_size=3)
    backend = BatchOnlyBackend()

    result = BB84Protocol().run(scenario, backend=backend)

    assert len(backend.batches) == 1
    assert len(backend.batches[0]) == scenario.pulses
    assert result.metrics.detected == scenario.pulses
    assert result.metrics.qber == 0.0
    assert len(result.event_sample) == 3
