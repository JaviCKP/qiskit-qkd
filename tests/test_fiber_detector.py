from __future__ import annotations

from dataclasses import replace

from qiskit_qkd.analysis import sweep_bb84_distance
from qiskit_qkd.channels import FiberChannel
from qiskit_qkd.config import ChannelConfig, DetectorConfig, Scenario, SourceConfig
from qiskit_qkd.detectors import ThresholdDetector
from qiskit_qkd.protocols import BB84Protocol


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


class ScriptedRng:
    def __init__(
        self,
        *,
        random_values: list[float],
        randrange_values: list[int] | None = None,
    ) -> None:
        self.random_values = list(random_values)
        self.randrange_values = list(randrange_values or [])

    def random(self) -> float:
        return self.random_values.pop(0)

    def randrange(self, stop: int) -> int:
        value = self.randrange_values.pop(0)
        assert 0 <= value < stop
        return value


def fiber_scenario(
    *,
    pulses: int = 1024,
    seed: int = 7,
    distance_km: float = 25.0,
    fixed_loss_db: float = 0.0,
    efficiency: float = 1.0,
    dark_count_rate_hz: float = 0.0,
    emission_probability: float = 1.0,
    store_full_event_log: bool = False,
) -> Scenario:
    return Scenario(
        pulses=pulses,
        clock_rate_hz=1_000_000.0,
        seed=seed,
        source=SourceConfig(emission_probability=emission_probability),
        channel=ChannelConfig(
            kind="fiber",
            distance_km=distance_km,
            attenuation_db_km=0.2,
            fixed_loss_db=fixed_loss_db,
        ),
        detector=DetectorConfig(
            kind="threshold",
            efficiency=efficiency,
            dark_count_rate_hz=dark_count_rate_hz,
            gate_width_s=1e-6,
        ),
        store_full_event_log=store_full_event_log,
    )


def test_fiber_transmittance_decreases_monotonically_with_distance() -> None:
    near = FiberChannel(distance_km=0.0, attenuation_db_km=0.2)
    middle = FiberChannel(distance_km=25.0, attenuation_db_km=0.2)
    far = FiberChannel(distance_km=100.0, attenuation_db_km=0.2)

    assert near.transmittance() == 1.0
    assert near.transmittance() > middle.transmittance() > far.transmittance()
    assert far.loss_db == 20.0


def test_total_effective_loss_without_dark_counts_has_no_detections() -> None:
    scenario = fiber_scenario(
        pulses=256,
        seed=13,
        fixed_loss_db=4_000.0,
        dark_count_rate_hz=0.0,
    )
    backend = FailingBackend()

    result = BB84Protocol().run(scenario, backend=backend)

    assert result.metrics.emitted == scenario.pulses
    assert result.metrics.transmitted == 0
    assert result.metrics.detected == 0


def test_zero_efficiency_without_dark_counts_has_no_detections() -> None:
    scenario = fiber_scenario(
        pulses=256,
        seed=17,
        distance_km=0.0,
        efficiency=0.0,
        dark_count_rate_hz=0.0,
    )

    result = BB84Protocol().run(scenario, backend=CountingBackend())

    assert result.metrics.transmitted == scenario.pulses
    assert result.metrics.detected == 0
    assert result.metrics.sifted == 0


def test_high_dark_counts_without_signal_create_random_bits() -> None:
    scenario = fiber_scenario(
        pulses=2_000,
        seed=19,
        emission_probability=0.0,
        dark_count_rate_hz=20_000_000.0,
        store_full_event_log=True,
    )

    result = BB84Protocol().run(scenario, backend=FailingBackend())
    dark_bits = [
        event.bob_bit
        for event in result.event_sample
        if event.detected and event.detection_origin == "dark"
    ]
    ones = sum(bit == 1 for bit in dark_bits)

    assert result.metrics.emitted == 0
    assert result.metrics.transmitted == 0
    assert result.metrics.detected >= 1_900
    assert all(bit in {0, 1} for bit in dark_bits)
    assert 0.45 <= ones / len(dark_bits) <= 0.55


def test_threshold_detector_resolves_double_click_policies() -> None:
    discard = ThresholdDetector(
        efficiency=1.0,
        dark_count_rate_hz=1_000.0,
        gate_width_s=1.0,
        double_click_policy="discard",
    ).detect(
        signal_present=True,
        measured_bit=1,
        rng=ScriptedRng(random_values=[0.0, 0.0]),
    )
    random = ThresholdDetector(
        efficiency=1.0,
        dark_count_rate_hz=1_000.0,
        gate_width_s=1.0,
        double_click_policy="random",
    ).detect(
        signal_present=True,
        measured_bit=1,
        rng=ScriptedRng(random_values=[0.0, 0.0], randrange_values=[0]),
    )
    error = ThresholdDetector(
        efficiency=1.0,
        dark_count_rate_hz=1_000.0,
        gate_width_s=1.0,
        double_click_policy="error",
    ).detect(
        signal_present=True,
        measured_bit=1,
        rng=ScriptedRng(random_values=[0.0, 0.0]),
    )

    assert discard.detected is False
    assert discard.detection_pattern == "double_click_discard"
    assert random.detected is True
    assert random.bob_bit == 0
    assert random.detection_pattern == "double_click_random"
    assert error.detected is True
    assert error.bob_bit == 0
    assert error.detection_pattern == "double_click_error"


def test_bb84_fiber_detects_less_at_longer_distance_with_same_seed() -> None:
    short = fiber_scenario(pulses=2_000, seed=23, distance_km=0.0)
    long = replace(short, channel=replace(short.channel, distance_km=100.0))

    short_result = BB84Protocol().run(short, backend=CountingBackend())
    long_result = BB84Protocol().run(long, backend=CountingBackend())

    assert short_result.metrics.detected == short.pulses
    assert long_result.metrics.detected < short_result.metrics.detected * 0.05


def test_same_seed_reproduces_same_fiber_summary() -> None:
    scenario = fiber_scenario(
        pulses=512,
        seed=29,
        distance_km=50.0,
        efficiency=0.35,
        dark_count_rate_hz=200.0,
    )

    first = BB84Protocol().run(scenario, backend=CountingBackend())
    second = BB84Protocol().run(scenario, backend=CountingBackend())

    assert first.summary() == second.summary()


def test_sweep_bb84_distance_returns_json_safe_rows() -> None:
    scenario = fiber_scenario(pulses=512, seed=31, efficiency=1.0)
    protocol = BB84Protocol()

    rows = sweep_bb84_distance(
        protocol,
        scenario,
        [0.0, 50.0],
        backend_factory=lambda _scenario: CountingBackend(),
    )

    assert [row["distance_km"] for row in rows] == [0.0, 50.0]
    assert rows[0]["detected"] > rows[1]["detected"]
    assert rows[0]["gain"] > rows[1]["gain"]
    assert set(rows[0]) >= {
        "distance_km",
        "loss_db",
        "qber",
        "detected",
        "sifted",
        "gain",
        "raw_detection_rate_hz",
        "sifted_key_rate_bps",
        "secret_key_rate_bps",
    }
