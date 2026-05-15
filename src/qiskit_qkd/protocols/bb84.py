"""Ideal BB84 protocol runner backed by Qiskit circuits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from qiskit_qkd.backends import QiskitSamplerBackend
from qiskit_qkd.channels import channel_from_config
from qiskit_qkd.config import Scenario
from qiskit_qkd.detectors import detector_from_config
from qiskit_qkd.postprocessing import bb84_secret_fraction, qber, sift_bb84_event
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.results import Event, Metrics, SimulationResult
from qiskit_qkd.timing import assign_timing

MeasureRound = tuple[int, str, str]


@dataclass(frozen=True, slots=True)
class PreparedRound:
    index: int
    time_s: float
    time_slot: int
    emission_time_s: float
    expected_arrival_time_s: float
    arrival_time_s: float | None
    bob_gate_start_s: float
    bob_gate_end_s: float
    signal_assigned_slot: int | None
    timing_status: str
    alice_bit: int
    alice_basis: str
    bob_basis: str
    emitted: bool
    photon_number: int
    transmitted: bool


class BB84Protocol:
    """Run BB84 prepare-and-measure simulations through Qiskit circuits."""

    def run(
        self,
        scenario: Scenario,
        backend: QiskitSamplerBackend | None = None,
    ) -> SimulationResult:
        """Run BB84 with event-level source, channel, and detector outcomes."""

        if scenario.protocol.name.lower() != "bb84":
            raise ValueError("BB84Protocol requires scenario.protocol.name='bb84'")

        backend = backend or QiskitSamplerBackend(seed=scenario.seed)
        rng = make_rng(scenario.seed)
        channel = channel_from_config(scenario.channel)
        detector = detector_from_config(scenario.detector)
        bases = tuple(scenario.protocol.basis_choices)
        batch_limit = getattr(backend, "max_circuits_per_job", scenario.pulses)
        event_sample: list[Event] = []
        emitted = 0
        transmitted = 0
        detected = 0
        sifted = 0
        errors = 0
        timing_discards = 0
        dead_time_discards = 0
        afterpulse_clicks = 0

        def consume(batch: Sequence[PreparedRound]) -> None:
            nonlocal emitted, transmitted, detected, sifted, errors
            nonlocal timing_discards, dead_time_discards, afterpulse_clicks
            measure_rounds = [
                (round_.alice_bit, round_.alice_basis, round_.bob_basis)
                for round_ in batch
                if round_.signal_assigned_slot is not None
            ]
            bob_bits = (
                self._measure_batch(backend, measure_rounds)
                if measure_rounds
                else ()
            )
            if len(bob_bits) != len(measure_rounds):
                raise ValueError("backend returned a different number of BB84 results")

            measured_bits = iter(bob_bits)
            for round_ in batch:
                signal_present = round_.signal_assigned_slot is not None
                measured_bit = next(measured_bits) if signal_present else None
                detector_time_s = (
                    round_.arrival_time_s
                    if signal_present and round_.arrival_time_s is not None
                    else (round_.bob_gate_start_s + round_.bob_gate_end_s) / 2
                )
                detection = detector.detect(
                    signal_present=signal_present,
                    measured_bit=measured_bit,
                    rng=rng,
                    time_s=detector_time_s,
                )
                timing_status = round_.timing_status
                if detection.blocked_by_dead_time:
                    timing_status = "dead_time"
                elif detection.detected and timing_status == "no_signal":
                    timing_status = "in_gate"
                assigned_slot = None
                if detection.detected:
                    assigned_slot = (
                        round_.signal_assigned_slot
                        if round_.signal_assigned_slot is not None
                        else round_.time_slot
                    )
                event = sift_bb84_event(
                    Event(
                        index=round_.index,
                        time_s=round_.time_s,
                        time_slot=round_.time_slot,
                        emission_time_s=round_.emission_time_s,
                        expected_arrival_time_s=round_.expected_arrival_time_s,
                        arrival_time_s=round_.arrival_time_s,
                        bob_gate_start_s=round_.bob_gate_start_s,
                        bob_gate_end_s=round_.bob_gate_end_s,
                        assigned_slot=assigned_slot,
                        timing_status=timing_status,
                        alice_bit=round_.alice_bit,
                        alice_basis=round_.alice_basis,
                        bob_basis=round_.bob_basis,
                        emitted=round_.emitted,
                        photon_number=round_.photon_number,
                        transmitted=round_.transmitted,
                        detected=detection.detected,
                        detection_origin=detection.detection_origin,
                        bob_bit=detection.bob_bit,
                        detection_pattern=detection.detection_pattern,
                    ),
                )
                emitted += int(event.emitted)
                transmitted += int(event.transmitted)
                detected += int(event.detected)
                sifted += int(event.sifted)
                errors += int(event.error is True)
                timing_discards += int(
                    event.transmitted and round_.signal_assigned_slot is None
                )
                dead_time_discards += int(detection.blocked_by_dead_time)
                afterpulse_clicks += int(detection.afterpulse)
                if scenario.store_full_event_log or (
                    len(event_sample) < scenario.event_sample_size
                ):
                    event_sample.append(event)

        pending: list[PreparedRound] = []
        for index in range(scenario.pulses):
            emitted_this_round = rng.random() < scenario.source.emission_probability
            photon_number = int(emitted_this_round)
            transmitted_this_round = (
                channel.transmit(rng) if emitted_this_round else False
            )
            timing = assign_timing(
                time_slot=index,
                pulses=scenario.pulses,
                clock_rate_hz=scenario.clock_rate_hz,
                gate_width_s=scenario.detector.gate_width_s,
                timing=scenario.timing,
                transmitted=transmitted_this_round,
                rng=rng,
            )
            pending.append(
                PreparedRound(
                    index=index,
                    time_s=timing.emission_time_s,
                    time_slot=timing.time_slot,
                    emission_time_s=timing.emission_time_s,
                    expected_arrival_time_s=timing.expected_arrival_time_s,
                    arrival_time_s=timing.arrival_time_s,
                    bob_gate_start_s=timing.bob_gate_start_s,
                    bob_gate_end_s=timing.bob_gate_end_s,
                    signal_assigned_slot=timing.signal_assigned_slot,
                    timing_status=timing.timing_status,
                    alice_bit=rng.randrange(2),
                    alice_basis=rng.choice(bases),
                    bob_basis=rng.choice(bases),
                    emitted=emitted_this_round,
                    photon_number=photon_number,
                    transmitted=transmitted_this_round,
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
            timing_discards=timing_discards,
            dead_time_discards=dead_time_discards,
            afterpulse_clicks=afterpulse_clicks,
            loss_db=channel.loss_db,
        )
        provenance = backend.provenance()
        provenance["protocol"] = "BB84"
        provenance["channel_model"] = type(channel).__name__
        provenance["detector_model"] = type(detector).__name__
        provenance["timing_model"] = "slot-gate"
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
        timing_discards: int,
        dead_time_discards: int,
        afterpulse_clicks: int,
        loss_db: float,
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
            timing_discards=timing_discards,
            dead_time_discards=dead_time_discards,
            afterpulse_clicks=afterpulse_clicks,
            qber=qber_value,
            loss_db=loss_db,
            gain=gain,
            raw_detection_rate_hz=raw_detection_rate_hz,
            sifted_key_rate_bps=sifted_key_rate_bps,
            secret_key_rate_bps=secret_key_rate_bps,
            abort=abort,
        )
