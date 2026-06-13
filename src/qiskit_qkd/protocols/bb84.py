"""Ideal BB84 protocol runner backed by Qiskit circuits."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from qiskit_qkd._json import JSONObject
from qiskit_qkd.backends import QiskitSamplerBackend, backend_from_scenario
from qiskit_qkd.channel_core import prepare_physical_round
from qiskit_qkd.channels import channel_from_config
from qiskit_qkd.channels.impairments import effective_background_count_rate_hz
from qiskit_qkd.config import Scenario
from qiskit_qkd.detectors import detector_from_config
from qiskit_qkd.eavesdroppers import eve_from_config
from qiskit_qkd.postprocessing import (
    bb84_secret_fraction,
    estimate_vacuum_weak_decoy_security,
    qber,
    run_bb84_classical_postprocessing,
    sift_bb84_event,
)
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.results import Event, Metrics, SimulationResult
from qiskit_qkd.sources import source_from_config

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
    surviving_photon_number: int
    intensity_class: str | None
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
        if scenario.source.kind in {"entangled_pair", "bell_pair", "e91"}:
            raise ValueError(
                "BB84Protocol requires a prepare-and-measure source; "
                "use E91Protocol for entangled-pair sources",
            )
        if scenario.dynamic.parameter_schedules:
            raise ValueError(
                "BB84Protocol.run does not resolve dynamic schedules; "
                "resolve the scenario first with temporal.scenario_at or "
                "use analysis.sweep_bb84_time",
            )

        backend = backend or backend_from_scenario(scenario)
        if hasattr(backend, "configure_from_scenario"):
            backend.configure_from_scenario(scenario)
        rng = make_rng(scenario.seed)
        sample_rng = make_rng(scenario.seed + 0xE7E17)
        source = source_from_config(scenario.source)
        channel = channel_from_config(scenario.channel)
        detector = detector_from_config(scenario.detector)
        eavesdropper = eve_from_config(scenario.eavesdropper)
        bases = tuple(scenario.protocol.basis_choices)
        sifting_enabled = scenario.post_processing.sifting_enabled
        background_count_rate_hz = effective_background_count_rate_hz(
            scenario.channel,
        )
        batch_limit = getattr(backend, "max_circuits_per_job", scenario.pulses)
        event_sample: list[Event] = []
        events_seen = 0
        bob_basis_by_slot: dict[int, str] = {}
        alice_sifted_bits: list[int] = []
        bob_sifted_bits: list[int] = []
        emitted = 0
        transmitted = 0
        detected = 0
        sifted = 0
        errors = 0
        timing_discards = 0
        dead_time_discards = 0
        afterpulse_clicks = 0
        eve_interceptions = 0
        eve_known_sifted_bits = 0
        decoy_stats: dict[str, dict[str, int]] = {}

        def record_event_sample(event: Event) -> None:
            nonlocal events_seen
            if scenario.store_full_event_log:
                event_sample.append(event)
                return
            if scenario.event_sample_size == 0:
                return
            events_seen += 1
            if len(event_sample) < scenario.event_sample_size:
                event_sample.append(event)
                return
            replacement = sample_rng.randrange(events_seen)
            if replacement < scenario.event_sample_size:
                event_sample[replacement] = event

        def consume(batch: Sequence[PreparedRound]) -> None:
            nonlocal emitted, transmitted, detected, sifted, errors
            nonlocal timing_discards, dead_time_discards, afterpulse_clicks
            nonlocal eve_interceptions, eve_known_sifted_bits
            attack_results = []
            measure_rounds = []
            for round_ in batch:
                if round_.signal_assigned_slot is None:
                    attack_results.append(None)
                    continue
                attack = eavesdropper.attack(
                    bit=round_.alice_bit,
                    basis=round_.alice_basis,
                    basis_choices=bases,
                    rng=rng,
                    photon_number=round_.photon_number,
                    surviving_photon_number=round_.surviving_photon_number,
                    intensity_class=round_.intensity_class,
                )
                attack_results.append(attack)
                eve_interceptions += int(attack.intercepted)
                if attack.block_signal:
                    continue
                bob_measurement_basis = bob_basis_by_slot[
                    round_.signal_assigned_slot
                ]
                measure_rounds.append(
                    (attack.resend_bit, attack.resend_basis, bob_measurement_basis),
                )
            bob_bits = (
                self._measure_batch(backend, measure_rounds)
                if measure_rounds
                else ()
            )
            if len(bob_bits) != len(measure_rounds):
                raise ValueError("backend returned a different number of BB84 results")

            measured_bits = iter(bob_bits)
            for round_, attack in zip(batch, attack_results, strict=True):
                attack_blocks_signal = bool(
                    attack is not None and attack.block_signal,
                )
                signal_present = (
                    round_.signal_assigned_slot is not None
                    and not attack_blocks_signal
                )
                measured_bit = next(measured_bits) if signal_present else None
                signal_photon_number = (
                    0
                    if not signal_present
                    else (
                        round_.surviving_photon_number
                        if attack is None
                        or attack.forwarded_photon_number is None
                        else attack.forwarded_photon_number
                    )
                )
                detector_time_s = (
                    round_.arrival_time_s
                    if signal_present and round_.arrival_time_s is not None
                    else (round_.bob_gate_start_s + round_.bob_gate_end_s) / 2
                )
                detection = detector.detect(
                    signal_present=signal_present,
                    signal_photon_number=signal_photon_number,
                    measured_bit=measured_bit,
                    rng=rng,
                    time_s=detector_time_s,
                    background_count_rate_hz=background_count_rate_hz,
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
                bob_basis = (
                    round_.bob_basis
                    if round_.signal_assigned_slot is None
                    else bob_basis_by_slot[round_.signal_assigned_slot]
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
                        bob_basis=bob_basis,
                        emitted=round_.emitted,
                        photon_number=round_.photon_number,
                        surviving_photon_number=round_.surviving_photon_number,
                        intensity_class=round_.intensity_class,
                        transmitted=round_.transmitted,
                        detected=detection.detected,
                        detection_origin=detection.detection_origin,
                        bob_bit=detection.bob_bit,
                        detection_pattern=detection.detection_pattern,
                        eve_action=(
                            None if attack is None else attack.eve_action
                        ),
                        eve_basis=None if attack is None else attack.eve_basis,
                        eve_detectable=(
                            False if attack is None else attack.eve_detectable
                        ),
                        tags={} if attack is None else attack.tags(),
                    ),
                    sifting_enabled=sifting_enabled,
                )
                emitted += int(event.emitted)
                transmitted += int(event.transmitted)
                detected += int(event.detected)
                sifted += int(event.sifted)
                errors += int(event.error is True)
                timing_discards += int(
                    event.transmitted
                    and round_.signal_assigned_slot != round_.time_slot
                )
                dead_time_discards += int(detection.blocked_by_dead_time)
                afterpulse_clicks += int(detection.afterpulse)
                self._record_decoy_event(decoy_stats, event)
                if (
                    event.sifted
                    and event.alice_bit is not None
                    and event.bob_bit is not None
                ):
                    alice_sifted_bits.append(event.alice_bit)
                    bob_sifted_bits.append(event.bob_bit)
                    if attack is not None and attack.eve_knows_alice_bit:
                        eve_known_sifted_bits += 1
                record_event_sample(event)

        pending: list[PreparedRound] = []
        for index in range(scenario.pulses):
            alice_bit = rng.randrange(2)
            alice_basis = rng.choice(bases)
            bob_basis = rng.choice(bases)
            bob_basis_by_slot[index] = bob_basis
            physical = prepare_physical_round(
                index=index,
                scenario=scenario,
                source=source,
                channel=channel,
                rng=rng,
                alice_bit=alice_bit,
                alice_basis=alice_basis,
            )
            pending.append(
                PreparedRound(
                    index=physical.index,
                    time_s=physical.time_s,
                    time_slot=physical.time_slot,
                    emission_time_s=physical.emission_time_s,
                    expected_arrival_time_s=physical.expected_arrival_time_s,
                    arrival_time_s=physical.arrival_time_s,
                    bob_gate_start_s=physical.bob_gate_start_s,
                    bob_gate_end_s=physical.bob_gate_end_s,
                    signal_assigned_slot=physical.signal_assigned_slot,
                    timing_status=physical.timing_status,
                    alice_bit=alice_bit,
                    alice_basis=alice_basis,
                    bob_basis=bob_basis,
                    emitted=physical.emitted,
                    photon_number=physical.photon_number,
                    surviving_photon_number=physical.surviving_photon_number,
                    intensity_class=physical.intensity_class,
                    transmitted=physical.transmitted,
                ),
            )
            while (
                len(pending) >= batch_limit
                and self._assigned_bob_bases_are_known(
                    pending[:batch_limit],
                    bob_basis_by_slot,
                )
            ):
                consume(pending[:batch_limit])
                del pending[:batch_limit]
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
            eve_interceptions=eve_interceptions,
            eve_known_sifted_bits=eve_known_sifted_bits,
            loss_db=channel.loss_db,
        )
        provenance = backend.provenance()
        provenance["protocol"] = "BB84"
        provenance["source_model"] = type(source).__name__
        provenance["channel_model"] = type(channel).__name__
        provenance["detector_model"] = type(detector).__name__
        provenance["eavesdropper_model"] = type(eavesdropper).__name__
        provenance["timing_model"] = "slot-gate"
        qiskit_summary = (
            backend.qiskit_summary()
            if hasattr(backend, "qiskit_summary")
            else {}
        )
        classical = run_bb84_classical_postprocessing(
            alice_bits=tuple(alice_sifted_bits),
            bob_bits=tuple(bob_sifted_bits),
            seed=scenario.seed,
            config=scenario.post_processing,
        ).to_dict()

        return SimulationResult(
            scenario=scenario,
            metrics=metrics,
            provenance=provenance,
            qiskit=qiskit_summary,
            classical=classical,
            decoy=self._decoy_summary(scenario, decoy_stats),
            event_sample=(
                tuple(event_sample)
                if scenario.store_full_event_log
                else tuple(sorted(event_sample, key=lambda event: event.index))
            ),
            aggregated=not scenario.store_full_event_log,
        )

    @staticmethod
    def _assigned_bob_bases_are_known(
        rounds: Sequence[PreparedRound],
        bob_basis_by_slot: dict[int, str],
    ) -> bool:
        return all(
            round_.signal_assigned_slot is None
            or round_.signal_assigned_slot in bob_basis_by_slot
            for round_ in rounds
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
        eve_interceptions: int,
        eve_known_sifted_bits: int,
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
        eve_intercepted_fraction = (
            eve_interceptions / transmitted if transmitted > 0 else 0.0
        )
        eve_information_estimate = (
            eve_known_sifted_bits / sifted if sifted > 0 else 0.0
        )

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
            eve_intercepted_fraction=eve_intercepted_fraction,
            eve_information_estimate=eve_information_estimate,
            qber=qber_value,
            loss_db=loss_db,
            gain=gain,
            raw_detection_rate_hz=raw_detection_rate_hz,
            sifted_key_rate_bps=sifted_key_rate_bps,
            secret_key_rate_bps=secret_key_rate_bps,
            abort=abort,
        )

    @staticmethod
    def _record_decoy_event(
        stats: dict[str, dict[str, int]],
        event: Event,
    ) -> None:
        if event.intensity_class is None:
            return
        row = stats.setdefault(
            event.intensity_class,
            {
                "pulses": 0,
                "emitted": 0,
                "zero_photon": 0,
                "single_photon": 0,
                "multi_photon": 0,
                "surviving_photons": 0,
                "transmitted": 0,
                "detected": 0,
                "sifted": 0,
                "errors": 0,
            },
        )
        row["pulses"] += 1
        row["emitted"] += int(event.emitted)
        row["zero_photon"] += int(event.photon_number == 0)
        row["single_photon"] += int(event.photon_number == 1)
        row["multi_photon"] += int(event.photon_number > 1)
        row["surviving_photons"] += event.surviving_photon_number
        row["transmitted"] += int(event.transmitted)
        row["detected"] += int(event.detected)
        row["sifted"] += int(event.sifted)
        row["errors"] += int(event.error is True)

    @staticmethod
    def _decoy_summary(
        scenario: Scenario,
        stats: dict[str, dict[str, int]],
    ) -> JSONObject:
        if not stats:
            return {}
        intensity_config = {
            intensity.name: intensity
            for intensity in scenario.source.decoy_intensities
        }
        summary: JSONObject = {}
        for intensity_class in sorted(stats):
            row = stats[intensity_class]
            pulses = row["pulses"]
            sifted = row["sifted"]
            config = intensity_config.get(intensity_class)
            output: JSONObject = {
                "pulses": pulses,
                "selection_fraction": pulses / scenario.pulses,
                "mean_photon_number": (
                    None if config is None else config.mean_photon_number
                ),
                "selection_probability": (
                    None if config is None else config.selection_probability
                ),
                "emitted": row["emitted"],
                "zero_photon": row["zero_photon"],
                "single_photon": row["single_photon"],
                "multi_photon": row["multi_photon"],
                "surviving_photons": row["surviving_photons"],
                "transmitted": row["transmitted"],
                "detected": row["detected"],
                "sifted": sifted,
                "errors": row["errors"],
                "gain": row["detected"] / pulses if pulses > 0 else 0.0,
                "qber": row["errors"] / sifted if sifted > 0 else 0.0,
            }
            summary[intensity_class] = output
        if (
            scenario.post_processing.decoy_security_estimation_enabled
            and scenario.post_processing.decoy_security_method
            == "vacuum_weak_asymptotic"
        ):
            summary["security"] = estimate_vacuum_weak_decoy_security(
                scenario,
                {
                    name: row
                    for name, row in summary.items()
                    if isinstance(row, dict)
                },
            )
        return summary
