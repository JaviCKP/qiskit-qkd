"""Ideal BB84 protocol runner backed by Qiskit circuits."""

from __future__ import annotations

from collections.abc import Sequence

from qiskit_qkd.backends import QiskitSamplerBackend
from qiskit_qkd.config import Scenario
from qiskit_qkd.postprocessing import bb84_secret_fraction, qber, sift_bb84_event
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.results import Event, Metrics, SimulationResult

PreparedRound = tuple[int, float, int, str, str]
MeasureRound = tuple[int, str, str]


class BB84Protocol:
    """Run a minimal ideal BB84 prepare-and-measure simulation."""

    def run(
        self,
        scenario: Scenario,
        backend: QiskitSamplerBackend | None = None,
    ) -> SimulationResult:
        """Run BB84 with ideal source, channel, and detector assumptions."""

        if scenario.protocol.name.lower() != "bb84":
            raise ValueError("BB84Protocol requires scenario.protocol.name='bb84'")

        backend = backend or QiskitSamplerBackend(seed=scenario.seed)
        rng = make_rng(scenario.seed)
        bases = tuple(scenario.protocol.basis_choices)
        batch_limit = getattr(backend, "max_circuits_per_job", scenario.pulses)
        event_sample: list[Event] = []
        emitted = 0
        transmitted = 0
        detected = 0
        sifted = 0
        errors = 0

        def consume(batch: Sequence[PreparedRound]) -> None:
            nonlocal emitted, transmitted, detected, sifted, errors
            measure_rounds = [
                (alice_bit, alice_basis, bob_basis)
                for _, _, alice_bit, alice_basis, bob_basis in batch
            ]
            bob_bits = self._measure_batch(backend, measure_rounds)
            if len(bob_bits) != len(batch):
                raise ValueError("backend returned a different number of BB84 results")

            for (
                index,
                time_s,
                alice_bit,
                alice_basis,
                bob_basis,
            ), bob_bit in zip(batch, bob_bits, strict=True):
                event = sift_bb84_event(
                    Event(
                        index=index,
                        time_s=time_s,
                        alice_bit=alice_bit,
                        alice_basis=alice_basis,
                        bob_basis=bob_basis,
                        emitted=True,
                        photon_number=1,
                        transmitted=True,
                        detected=True,
                        detection_origin="signal",
                        bob_bit=bob_bit,
                    ),
                )
                emitted += int(event.emitted)
                transmitted += int(event.transmitted)
                detected += int(event.detected)
                sifted += int(event.sifted)
                errors += int(event.error is True)
                if scenario.store_full_event_log or (
                    len(event_sample) < scenario.event_sample_size
                ):
                    event_sample.append(event)

        pending: list[PreparedRound] = []
        for index in range(scenario.pulses):
            pending.append(
                (
                    index,
                    index / scenario.clock_rate_hz,
                    rng.randrange(2),
                    rng.choice(bases),
                    rng.choice(bases),
                ),
            )
            if len(pending) == batch_limit:
                consume(pending)
                pending.clear()
        if pending:
            consume(pending)

        metrics = self._metrics_from_counts(
            scenario,
            emitted=emitted,
            transmitted=transmitted,
            detected=detected,
            sifted=sifted,
            errors=errors,
        )
        provenance = backend.provenance()
        provenance["protocol"] = "BB84"
        qiskit_summary = (
            backend.qiskit_summary()
            if hasattr(backend, "qiskit_summary")
            else {}
        )

        return SimulationResult(
            scenario=scenario,
            metrics=metrics,
            provenance=provenance,
            qiskit=qiskit_summary,
            event_sample=tuple(event_sample),
            aggregated=not scenario.store_full_event_log,
        )

    @staticmethod
    def _measure_batch(
        backend: QiskitSamplerBackend,
        rounds: Sequence[MeasureRound],
    ) -> tuple[int, ...]:
        if hasattr(backend, "measure_bb84_batch"):
            return tuple(backend.measure_bb84_batch(rounds))
        return tuple(
            backend.measure_bb84(bit, alice_basis, bob_basis)
            for bit, alice_basis, bob_basis in rounds
        )

    @staticmethod
    def _metrics_from_counts(
        scenario: Scenario,
        *,
        emitted: int,
        transmitted: int,
        detected: int,
        sifted: int,
        errors: int,
    ) -> Metrics:
        qber_value = qber(errors, sifted)
        gain = detected / scenario.pulses
        raw_detection_rate_hz = gain * scenario.clock_rate_hz
        sifted_key_rate_bps = (sifted / scenario.pulses) * scenario.clock_rate_hz
        secret_fraction = bb84_secret_fraction(
            qber_value,
            error_correction_efficiency=(
                scenario.post_processing.error_correction_efficiency
            ),
        )
        threshold = scenario.post_processing.qber_abort_threshold
        abort = threshold is not None and qber_value > threshold
        secret_key_rate_bps = 0.0 if abort else sifted_key_rate_bps * secret_fraction

        return Metrics(
            pulses=scenario.pulses,
            emitted=emitted,
            transmitted=transmitted,
            detected=detected,
            sifted=sifted,
            errors=errors,
            qber=qber_value,
            loss_db=0.0,
            gain=gain,
            raw_detection_rate_hz=raw_detection_rate_hz,
            sifted_key_rate_bps=sifted_key_rate_bps,
            secret_key_rate_bps=secret_key_rate_bps,
            abort=abort,
        )
