"""Entanglement-based E91 protocol runner backed by Qiskit circuits."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from qiskit_qkd._json import JSONObject
from qiskit_qkd._validation import require_probability
from qiskit_qkd.backends import backend_from_scenario
from qiskit_qkd.channels import channel_from_config
from qiskit_qkd.channels.impairments import (
    effective_background_count_rate_hz,
    effective_jitter_std_s,
)
from qiskit_qkd.config import Scenario, require_executable_scenario
from qiskit_qkd.detectors import DetectionResult, detector_from_config
from qiskit_qkd.postprocessing import (
    bb84_secret_fraction,
    chsh_s_from_correlations,
    correlation_from_counts,
    e91_key_error,
    qber,
    setting_pair_label,
)
from qiskit_qkd.reproducibility import make_rng
from qiskit_qkd.results import Event, Metrics, SimulationResult
from qiskit_qkd.sources import source_from_config
from qiskit_qkd.timing import (
    TimingContext,
    assign_timing,
    timing_context_from_scenario,
)

CancellationCheck = Callable[[], None]


def _check_cancellation(check: CancellationCheck | None) -> None:
    if check is not None:
        check()


@dataclass(frozen=True, slots=True)
class PreparedE91Round:
    """Event-layer state prepared before the Bell circuit batch is executed."""

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
    alice_setting: int
    bob_setting: int
    alice_angle_rad: float
    bob_angle_rad: float
    emitted: bool
    bob_transmitted: bool


class E91Protocol:
    """Run E91 with Bell-pair circuits, event-layer loss, and CHSH diagnostics."""

    def run(
        self,
        scenario: Scenario,
        *,
        backend: Any | None = None,
        cancellation_check: CancellationCheck | None = None,
    ) -> SimulationResult:
        _check_cancellation(cancellation_check)
        if scenario.protocol.name.lower() != "e91":
            raise ValueError("E91Protocol requires scenario.protocol.name='e91'")
        if scenario.source.kind.lower() not in {"entangled_pair", "bell_pair", "e91"}:
            raise ValueError("E91Protocol requires an entangled-pair source")
        if scenario.eavesdropper.kind != "none":
            raise ValueError(
                "E91Protocol has no eavesdropper models; "
                "set eavesdropper kind to 'none' or use BB84Protocol",
            )
        require_executable_scenario(scenario)
        if scenario.dynamic.parameter_schedules:
            raise ValueError(
                "E91Protocol.run does not resolve dynamic schedules; "
                "resolve the scenario first with temporal.scenario_at",
            )

        backend = backend or backend_from_scenario(scenario)
        if hasattr(backend, "configure_from_scenario"):
            backend.configure_from_scenario(scenario)

        # Aggregated runs use the bounded-memory streaming path.  The legacy
        # full-event-log path below intentionally keeps its historical
        # all-round representation for compatibility with callers requesting
        # every event explicitly.
        if not scenario.store_full_event_log:
            return self._run_streaming(
                scenario,
                backend=backend,
                cancellation_check=cancellation_check,
            )

        rng = make_rng(scenario.seed)
        source = source_from_config(scenario.source)
        channel = channel_from_config(scenario.channel)
        alice_detector = detector_from_config(scenario.detector)
        bob_detector = detector_from_config(scenario.detector)

        prepared = []
        for index in range(scenario.pulses):
            if index % 256 == 0:
                _check_cancellation(cancellation_check)
            prepared.append(
                self._prepare_round(
                    index=index,
                    scenario=scenario,
                    source=source,
                    channel=channel,
                    rng=rng,
                ),
            )
        _check_cancellation(cancellation_check)
        measured_pairs = self._measure_emitted_pairs(
            backend,
            scenario,
            prepared,
        )
        _check_cancellation(cancellation_check)
        events = self._resolve_events(
            scenario=scenario,
            prepared=prepared,
            measured_pairs=measured_pairs,
            alice_detector=alice_detector,
            bob_detector=bob_detector,
            rng=rng,
            cancellation_check=cancellation_check,
        )

        setting_rows = _setting_rows(scenario, events)
        chsh_s = _chsh_s_from_rows(scenario, setting_rows)
        metrics = self._metrics_from_events(
            scenario,
            events,
            channel.loss_db,
            chsh_s=chsh_s,
        )
        bell = self._bell_summary(scenario, setting_rows, metrics.chsh_s)
        provenance = backend.provenance()
        provenance["protocol"] = "E91"
        provenance["source_model"] = type(source).__name__
        provenance["channel_model"] = type(channel).__name__
        provenance["detector_model"] = type(bob_detector).__name__
        qiskit_summary = (
            backend.qiskit_summary()
            if hasattr(backend, "qiskit_summary")
            else {}
        )
        observed_qber = qber(metrics.errors, metrics.sifted)
        threshold = scenario.post_processing.qber_abort_threshold
        threshold_exceeded = (
            None
            if observed_qber is None or threshold is None
            else observed_qber > threshold
        )
        classical = {
            "protocol": "E91",
            "coincidences": metrics.detected,
            "sifted_key_length": metrics.sifted,
            "errors": metrics.errors,
            "qber": observed_qber,
            "estimated_qber": observed_qber,
            "qber_defined": observed_qber is not None,
            "qber_sample_size": metrics.sifted,
            "qber_method": (
                "full_sifted_key_diagnostic"
                if observed_qber is not None
                else "unavailable"
            ),
            "threshold": threshold,
            "threshold_exceeded": threshold_exceeded,
            "threshold_decision_source": (
                "disabled"
                if threshold is None
                else "unavailable"
                if observed_qber is None
                else "metrics_legacy"
            ),
            "verification_status": "not_performed",
            "secret_rate_model": "pedagogical_bb84_asymptotic_qber_fraction",
            "chsh_s": metrics.chsh_s,
            "classical_bound": bell["classical_bound"],
            "observed_threshold_exceeded": bell["observed_threshold_exceeded"],
            "bell_violation": bell["bell_violation"],
            "bell_violation_legacy_projection_of": bell[
                "bell_violation_legacy_projection_of"
            ],
            "bell_violation_legacy_none_maps_to": bell[
                "bell_violation_legacy_none_maps_to"
            ],
        }

        event_sample = (
            tuple(events)
            if scenario.store_full_event_log
            else _sample_event_records(
                events,
                sample_size=scenario.event_sample_size,
                seed=scenario.seed,
            )
        )
        return SimulationResult(
            scenario=scenario,
            metrics=metrics,
            provenance=provenance,
            qiskit=qiskit_summary,
            classical=classical,
            bell=bell,
            event_sample=event_sample,
            aggregated=not scenario.store_full_event_log,
        )

    def _run_streaming(
        self,
        scenario: Scenario,
        *,
        backend: Any,
        cancellation_check: CancellationCheck | None,
    ) -> SimulationResult:
        """Run an aggregated E91 simulation without retaining all rounds.

        The protocol historically consumed one RNG stream in two phases:
        preparation for every pulse, followed by detector sampling for every
        pulse.  Streaming detector work as soon as a preparation block is
        ready would change that order.  We therefore make a first, discarded
        preparation pass to advance the RNG to the detector phase and then
        regenerate the same rounds block-by-block.  This keeps scientific
        values and RNG state identical while bounding live round/event memory.
        """

        configured_limit = getattr(backend, "max_circuits_per_job", 256)
        try:
            block_limit = max(1, int(configured_limit))
        except (TypeError, ValueError):
            block_limit = 256
        timing_context = timing_context_from_scenario(scenario)

        preparation_rng = make_rng(scenario.seed)
        preparation_source = source_from_config(scenario.source)
        preparation_channel = channel_from_config(scenario.channel)
        for start in range(0, scenario.pulses, block_limit):
            _check_cancellation(cancellation_check)
            stop = min(start + block_limit, scenario.pulses)
            for index in range(start, stop):
                self._prepare_round(
                    index=index,
                    scenario=scenario,
                    source=preparation_source,
                    channel=preparation_channel,
                    rng=preparation_rng,
                    timing_context=timing_context,
                )
        _check_cancellation(cancellation_check)

        # ``preparation_rng`` now has exactly the state used by the historical
        # detector phase.  A fresh RNG regenerates preparation blocks, while
        # this one feeds detector sampling in the original order.
        detector_rng = preparation_rng
        round_rng = make_rng(scenario.seed)
        source = source_from_config(scenario.source)
        channel = channel_from_config(scenario.channel)
        alice_detector = detector_from_config(scenario.detector)
        bob_detector = detector_from_config(scenario.detector)

        setting_counters = _new_setting_counters(scenario)
        sample_rng = make_rng(scenario.seed + 0xE7E17)
        event_sample: list[Event] = []
        events_seen = 0
        emitted = 0
        transmitted = 0
        detected = 0
        sifted = 0
        errors = 0
        timing_discards = 0
        dead_time_discards = 0
        afterpulse_clicks = 0

        for start in range(0, scenario.pulses, block_limit):
            _check_cancellation(cancellation_check)
            stop = min(start + block_limit, scenario.pulses)
            prepared = [
                self._prepare_round(
                    index=index,
                    scenario=scenario,
                    source=source,
                    channel=channel,
                    rng=round_rng,
                    timing_context=timing_context,
                )
                for index in range(start, stop)
            ]
            measured_pairs = self._measure_emitted_pairs(
                backend,
                scenario,
                prepared,
            )
            _check_cancellation(cancellation_check)
            events = self._resolve_events(
                scenario=scenario,
                prepared=prepared,
                measured_pairs=measured_pairs,
                alice_detector=alice_detector,
                bob_detector=bob_detector,
                rng=detector_rng,
                cancellation_check=None,
            )
            for event in events:
                emitted += int(event.emitted)
                transmitted += int(event.transmitted)
                detected += int(event.detected)
                sifted += int(event.sifted)
                errors += int(event.error is True)
                timing_discards += int(_e91_timing_discard(event))
                dead_time_discards += int(
                    event.tags.get("alice_blocked_by_dead_time") is True
                    or event.tags.get("bob_blocked_by_dead_time") is True
                )
                afterpulse_clicks += int(
                    event.tags.get("alice_afterpulse") is True
                    or event.tags.get("bob_afterpulse") is True
                )
                _update_setting_counter(setting_counters, event)

                if scenario.event_sample_size > 0:
                    events_seen += 1
                    if len(event_sample) < scenario.event_sample_size:
                        event_sample.append(event)
                    else:
                        replacement = sample_rng.randrange(events_seen)
                        if replacement < scenario.event_sample_size:
                            event_sample[replacement] = event
            _check_cancellation(cancellation_check)

        setting_rows = _setting_rows_from_counters(scenario, setting_counters)
        chsh_s = _chsh_s_from_rows(scenario, setting_rows)
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
            chsh_s=chsh_s,
        )
        return self._assemble_result(
            scenario,
            backend=backend,
            source=source,
            channel=channel,
            detector=bob_detector,
            metrics=metrics,
            setting_rows=setting_rows,
            event_sample=tuple(sorted(event_sample, key=lambda event: event.index)),
            aggregated=True,
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
        chsh_s: float | None,
    ) -> Metrics:
        observed_qber = qber(errors, sifted)
        legacy_qber = 0.0 if observed_qber is None else observed_qber
        gain = detected / scenario.pulses
        raw_detection_rate_hz = gain * scenario.clock_rate_hz
        sifted_key_rate_bps = (sifted / scenario.pulses) * scenario.clock_rate_hz
        secret_fraction = (
            0.0
            if observed_qber is None
            else bb84_secret_fraction(
                observed_qber,
                error_correction_efficiency=(
                    scenario.post_processing.error_correction_efficiency
                ),
            )
        )
        threshold = scenario.post_processing.qber_abort_threshold
        abort = (
            observed_qber is not None
            and threshold is not None
            and observed_qber > threshold
        )
        return Metrics(
            pulses=scenario.pulses,
            emitted=emitted,
            transmitted=transmitted,
            detected=detected,
            sifted=sifted,
            errors=errors,
            qber=legacy_qber,
            loss_db=loss_db,
            gain=gain,
            raw_detection_rate_hz=raw_detection_rate_hz,
            sifted_key_rate_bps=sifted_key_rate_bps,
            secret_key_rate_bps=(
                0.0 if abort else sifted_key_rate_bps * secret_fraction
            ),
            abort=abort,
            timing_discards=timing_discards,
            dead_time_discards=dead_time_discards,
            afterpulse_clicks=afterpulse_clicks,
            chsh_s=chsh_s,
        )

    @staticmethod
    def _assemble_result(
        scenario: Scenario,
        *,
        backend: Any,
        source: Any,
        channel: Any,
        detector: Any,
        metrics: Metrics,
        setting_rows: list[JSONObject],
        event_sample: tuple[Event, ...],
        aggregated: bool,
    ) -> SimulationResult:
        bell = E91Protocol._bell_summary(scenario, setting_rows, metrics.chsh_s)
        provenance = backend.provenance()
        provenance["protocol"] = "E91"
        provenance["source_model"] = type(source).__name__
        provenance["channel_model"] = type(channel).__name__
        provenance["detector_model"] = type(detector).__name__
        qiskit_summary = (
            backend.qiskit_summary()
            if hasattr(backend, "qiskit_summary")
            else {}
        )
        observed_qber = qber(metrics.errors, metrics.sifted)
        threshold = scenario.post_processing.qber_abort_threshold
        threshold_exceeded = (
            None
            if observed_qber is None or threshold is None
            else observed_qber > threshold
        )
        classical = {
            "protocol": "E91",
            "coincidences": metrics.detected,
            "sifted_key_length": metrics.sifted,
            "errors": metrics.errors,
            "qber": observed_qber,
            "estimated_qber": observed_qber,
            "qber_defined": observed_qber is not None,
            "qber_sample_size": metrics.sifted,
            "qber_method": (
                "full_sifted_key_diagnostic"
                if observed_qber is not None
                else "unavailable"
            ),
            "threshold": threshold,
            "threshold_exceeded": threshold_exceeded,
            "threshold_decision_source": (
                "disabled"
                if threshold is None
                else "unavailable"
                if observed_qber is None
                else "metrics_legacy"
            ),
            "verification_status": "not_performed",
            "secret_rate_model": "pedagogical_bb84_asymptotic_qber_fraction",
            "chsh_s": metrics.chsh_s,
            "classical_bound": bell["classical_bound"],
            "observed_threshold_exceeded": bell["observed_threshold_exceeded"],
            "bell_violation": bell["bell_violation"],
            "bell_violation_legacy_projection_of": bell[
                "bell_violation_legacy_projection_of"
            ],
            "bell_violation_legacy_none_maps_to": bell[
                "bell_violation_legacy_none_maps_to"
            ],
        }
        return SimulationResult(
            scenario=scenario,
            metrics=metrics,
            provenance=provenance,
            qiskit=qiskit_summary,
            classical=classical,
            bell=bell,
            event_sample=event_sample,
            aggregated=aggregated,
        )

    @staticmethod
    def _prepare_round(
        *,
        index: int,
        scenario: Scenario,
        source: Any,
        channel: Any,
        rng: random.Random,
        timing_context: TimingContext | None = None,
    ) -> PreparedE91Round:
        slot_period_s = (
            timing_context.slot_period_s
            if timing_context is not None
            else 1.0 / scenario.clock_rate_hz
        )
        emission_time_s = index * slot_period_s
        emission = source.emit(rng=rng, time_s=emission_time_s)
        bob_transmitted = (
            emission.emitted
            and _sample_single_photon_survival(channel=channel, rng=rng)
        )
        effective_timing = (
            timing_context.timing
            if timing_context is not None
            else replace(
                scenario.timing,
                jitter_std_s=effective_jitter_std_s(scenario),
            )
        )
        timing = assign_timing(
            time_slot=index,
            pulses=scenario.pulses,
            clock_rate_hz=scenario.clock_rate_hz,
            gate_width_s=scenario.detector.gate_width_s,
            timing=effective_timing,
            transmitted=bob_transmitted,
            rng=rng,
            context=timing_context,
        )
        alice_setting = rng.randrange(len(scenario.e91.alice_angles_rad))
        bob_setting = rng.randrange(len(scenario.e91.bob_angles_rad))
        return PreparedE91Round(
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
            alice_setting=alice_setting,
            bob_setting=bob_setting,
            alice_angle_rad=scenario.e91.alice_angles_rad[alice_setting],
            bob_angle_rad=scenario.e91.bob_angles_rad[bob_setting],
            emitted=emission.emitted,
            bob_transmitted=bob_transmitted,
        )

    @staticmethod
    def _measure_emitted_pairs(
        backend: Any,
        scenario: Scenario,
        prepared: Sequence[PreparedE91Round],
    ) -> dict[int, tuple[int, int]]:
        emitted_rounds = [round_ for round_ in prepared if round_.emitted]
        circuit_rounds = [
            (
                round_.alice_angle_rad,
                round_.bob_angle_rad,
                scenario.e91.bell_state,
            )
            for round_ in emitted_rounds
        ]
        can_omit = getattr(backend, "can_omit_e91_unused_results", None)
        measure_selected = getattr(backend, "measure_e91_batch_selected", None)
        use_selected = (
            not scenario.store_full_event_log
            and scenario.event_sample_size == 0
            and callable(can_omit)
            and can_omit()
            and callable(measure_selected)
        )
        if circuit_rounds and use_selected:
            required = [
                _e91_bob_signal_in_coincidence_window(round_)
                for round_ in emitted_rounds
            ]
            measured = measure_selected(circuit_rounds, required)
        else:
            measured = (
                backend.measure_e91_batch(circuit_rounds)
                if circuit_rounds
                else ()
            )
        if len(measured) != len(circuit_rounds):
            raise ValueError("backend returned a different number of E91 results")
        measured_by_index: dict[int, tuple[int, int]] = {}
        for round_, measured_pair in zip(emitted_rounds, measured, strict=True):
            # The placeholder is never observable: selected omission is enabled
            # only without event export, and non-coincident bits do not enter E91
            # setting correlations or detector state transitions.
            measured_by_index[round_.index] = (
                (0, 0) if measured_pair is None else measured_pair
            )
        return measured_by_index

    @staticmethod
    def _resolve_events(
        *,
        scenario: Scenario,
        prepared: Sequence[PreparedE91Round],
        measured_pairs: dict[int, tuple[int, int]],
        alice_detector: Any,
        bob_detector: Any,
        rng: random.Random,
        cancellation_check: CancellationCheck | None = None,
    ) -> list[Event]:
        events: list[Event] = []
        alice_background_rate_hz = 0.0
        bob_background_rate_hz = effective_background_count_rate_hz(scenario.channel)
        key_pairs = set(scenario.e91.key_setting_pairs)
        for index, round_ in enumerate(prepared):
            if index % 256 == 0:
                _check_cancellation(cancellation_check)
            measured_pair = measured_pairs.get(round_.index)
            alice_measured_bit = None if measured_pair is None else measured_pair[0]
            bob_measured_bit = None if measured_pair is None else measured_pair[1]

            alice_detection = alice_detector.detect(
                signal_present=round_.emitted,
                signal_photon_number=1 if round_.emitted else 0,
                measured_bit=alice_measured_bit if round_.emitted else None,
                rng=rng,
                time_s=round_.emission_time_s,
                background_count_rate_hz=alice_background_rate_hz,
            )
            bob_signal_present = _e91_bob_signal_in_coincidence_window(round_)
            bob_detection = bob_detector.detect(
                signal_present=bob_signal_present,
                signal_photon_number=1 if bob_signal_present else 0,
                measured_bit=bob_measured_bit if bob_signal_present else None,
                rng=rng,
                time_s=(
                    round_.arrival_time_s
                    if bob_signal_present and round_.arrival_time_s is not None
                    else (round_.bob_gate_start_s + round_.bob_gate_end_s) / 2
                ),
                background_count_rate_hz=bob_background_rate_hz,
            )
            coincidence = alice_detection.detected and bob_detection.detected
            setting_pair = (round_.alice_setting, round_.bob_setting)
            sifted = coincidence and setting_pair in key_pairs
            error = (
                e91_key_error(
                    alice_detection.bob_bit,
                    bob_detection.bob_bit,
                    bob_key_bit_flip=scenario.e91.bob_key_bit_flip,
                )
                if sifted
                and alice_detection.bob_bit is not None
                and bob_detection.bob_bit is not None
                else None
            )
            tags = _event_tags(
                round_=round_,
                alice_detection=alice_detection,
                bob_detection=bob_detection,
                coincidence=coincidence,
                used_for_key=setting_pair in key_pairs,
                used_for_chsh=_setting_used_for_chsh(scenario, setting_pair),
            )
            events.append(
                Event(
                    index=round_.index,
                    time_s=round_.time_s,
                    time_slot=round_.time_slot,
                    emission_time_s=round_.emission_time_s,
                    expected_arrival_time_s=round_.expected_arrival_time_s,
                    arrival_time_s=round_.arrival_time_s,
                    bob_gate_start_s=round_.bob_gate_start_s,
                    bob_gate_end_s=round_.bob_gate_end_s,
                    assigned_slot=round_.signal_assigned_slot,
                    timing_status=round_.timing_status,
                    alice_bit=alice_detection.bob_bit,
                    alice_basis=f"A{round_.alice_setting}",
                    bob_basis=f"B{round_.bob_setting}",
                    emitted=round_.emitted,
                    photon_number=2 if round_.emitted else 0,
                    surviving_photon_number=(
                        int(round_.emitted) + int(round_.bob_transmitted)
                    ),
                    intensity_class="entangled_pair" if round_.emitted else None,
                    transmitted=round_.bob_transmitted,
                    detected=coincidence,
                    detection_origin=_combined_detection_origin(
                        alice_detection,
                        bob_detection,
                        coincidence,
                    ),
                    bob_bit=bob_detection.bob_bit,
                    detection_pattern=(
                        "coincidence" if coincidence else "no_coincidence"
                    ),
                    sifted=sifted,
                    error=error,
                    party="alice_bob",
                    bsm_success=coincidence,
                    tags=tags,
                ),
            )
        return events

    @staticmethod
    def _metrics_from_events(
        scenario: Scenario,
        events: Sequence[Event],
        loss_db: float,
        *,
        chsh_s: float | None,
    ) -> Metrics:
        emitted = sum(int(event.emitted) for event in events)
        transmitted = sum(int(event.transmitted) for event in events)
        detected = sum(int(event.detected) for event in events)
        sifted = sum(int(event.sifted) for event in events)
        errors = sum(int(event.error is True) for event in events)
        observed_qber = qber(errors, sifted)
        # Preserve Metrics.qber as the schema-v1 numeric projection only.
        legacy_qber = 0.0 if observed_qber is None else observed_qber
        gain = detected / scenario.pulses
        raw_detection_rate_hz = gain * scenario.clock_rate_hz
        sifted_key_rate_bps = (sifted / scenario.pulses) * scenario.clock_rate_hz
        secret_fraction = (
            0.0
            if observed_qber is None
            else bb84_secret_fraction(
                observed_qber,
                error_correction_efficiency=(
                    scenario.post_processing.error_correction_efficiency
                ),
            )
        )
        threshold = scenario.post_processing.qber_abort_threshold
        abort = (
            observed_qber is not None
            and threshold is not None
            and observed_qber > threshold
        )
        return Metrics(
            pulses=scenario.pulses,
            emitted=emitted,
            transmitted=transmitted,
            detected=detected,
            sifted=sifted,
            errors=errors,
            qber=legacy_qber,
            loss_db=loss_db,
            gain=gain,
            raw_detection_rate_hz=raw_detection_rate_hz,
            sifted_key_rate_bps=sifted_key_rate_bps,
            secret_key_rate_bps=(
                0.0 if abort else sifted_key_rate_bps * secret_fraction
            ),
            abort=abort,
            timing_discards=sum(
                int(_e91_timing_discard(event))
                for event in events
            ),
            dead_time_discards=sum(
                int(
                    event.tags.get("alice_blocked_by_dead_time") is True
                    or event.tags.get("bob_blocked_by_dead_time") is True
                )
                for event in events
            ),
            afterpulse_clicks=sum(
                int(
                    event.tags.get("alice_afterpulse") is True
                    or event.tags.get("bob_afterpulse") is True
                )
                for event in events
            ),
            chsh_s=chsh_s,
        )

    @staticmethod
    def _bell_summary(
        scenario: Scenario,
        setting_rows: list[JSONObject],
        chsh_s: float | None,
    ) -> JSONObject:
        chsh_sample_size_by_term = {
            str(row["setting_pair"]): int(row["coincidences"])
            for row in setting_rows
            if row.get("used_for_chsh") is True
        }
        chsh_sample_size = sum(chsh_sample_size_by_term.values())
        observed_chsh_s = chsh_s if chsh_sample_size > 0 else None
        classical_bound = scenario.e91.classical_bound
        observed_threshold_exceeded = (
            None
            if observed_chsh_s is None
            else observed_chsh_s > classical_bound
        )
        return {
            "protocol": "E91",
            "bell_state": scenario.e91.bell_state,
            "chsh_enabled": scenario.e91.chsh_estimation_enabled,
            "chsh_s": chsh_s,
            "observed_chsh_s": observed_chsh_s,
            "chsh_sample_size": chsh_sample_size,
            "chsh_sample_size_by_term": chsh_sample_size_by_term,
            "classical_bound": classical_bound,
            "observed_threshold_exceeded": observed_threshold_exceeded,
            "conclusion_scope": "diagnostic_fair_sampling_no_significance_test",
            # Schema-v1 compatibility projection retained for existing consumers.
            # It is lossy: an unavailable observation (None) maps to False.
            "bell_violation": observed_threshold_exceeded is True,
            "bell_violation_legacy_projection_of": "observed_threshold_exceeded",
            "bell_violation_legacy_none_maps_to": False,
            "key_setting_pairs": [
                setting_pair_label(alice, bob)
                for alice, bob in scenario.e91.key_setting_pairs
            ],
            "chsh_terms": [
                {
                    "setting_pair": setting_pair_label(alice, bob),
                    "coefficient": coefficient,
                }
                for alice, bob, coefficient in scenario.e91.chsh_terms
            ],
            "setting_rows": setting_rows,
        }


def _sample_single_photon_survival(*, channel: Any, rng: random.Random) -> bool:
    if hasattr(channel, "sample_transmittance"):
        eta = require_probability(
            "channel.sample_transmittance",
            channel.sample_transmittance(rng),
        )
        return rng.random() < eta
    if hasattr(channel, "transmittance"):
        eta = require_probability("channel.transmittance", channel.transmittance())
        return rng.random() < eta
    return bool(channel.transmit(rng))


def _sample_event_records(
    events: Sequence[Event],
    *,
    sample_size: int,
    seed: int,
) -> tuple[Event, ...]:
    if sample_size == 0:
        return ()
    sample_rng = make_rng(seed + 0xE7E17)
    sample: list[Event] = []
    for seen, event in enumerate(events, start=1):
        if len(sample) < sample_size:
            sample.append(event)
            continue
        replacement = sample_rng.randrange(seen)
        if replacement < sample_size:
            sample[replacement] = event
    return tuple(sorted(sample, key=lambda event: event.index))


def _e91_bob_signal_in_coincidence_window(round_: PreparedE91Round) -> bool:
    return round_.signal_assigned_slot == round_.time_slot


def _e91_timing_discard(event: Event) -> bool:
    return event.transmitted and event.assigned_slot != event.time_slot


def _setting_used_for_chsh(scenario: Scenario, setting_pair: tuple[int, int]) -> bool:
    return any(
        (alice, bob) == setting_pair
        for alice, bob, _coefficient in scenario.e91.chsh_terms
    )


def _event_tags(
    *,
    round_: PreparedE91Round,
    alice_detection: DetectionResult,
    bob_detection: DetectionResult,
    coincidence: bool,
    used_for_key: bool,
    used_for_chsh: bool,
) -> JSONObject:
    return {
        "alice_setting": round_.alice_setting,
        "bob_setting": round_.bob_setting,
        "setting_pair": setting_pair_label(round_.alice_setting, round_.bob_setting),
        "alice_angle_rad": round_.alice_angle_rad,
        "bob_angle_rad": round_.bob_angle_rad,
        "alice_detection_origin": alice_detection.detection_origin,
        "bob_detection_origin": bob_detection.detection_origin,
        "alice_detection_pattern": alice_detection.detection_pattern,
        "bob_detection_pattern": bob_detection.detection_pattern,
        "alice_blocked_by_dead_time": alice_detection.blocked_by_dead_time,
        "bob_blocked_by_dead_time": bob_detection.blocked_by_dead_time,
        "alice_afterpulse": alice_detection.afterpulse,
        "bob_afterpulse": bob_detection.afterpulse,
        "coincidence": coincidence,
        "used_for_key": used_for_key,
        "used_for_chsh": used_for_chsh,
    }


def _combined_detection_origin(
    alice_detection: DetectionResult,
    bob_detection: DetectionResult,
    coincidence: bool,
) -> str:
    if not coincidence:
        return "none"
    origins = {alice_detection.detection_origin, bob_detection.detection_origin}
    for origin in ("background", "dark", "afterpulse"):
        if origin in origins:
            return origin
    return "signal"


def _setting_rows(scenario: Scenario, events: Sequence[Event]) -> list[JSONObject]:
    counters = _new_setting_counters(scenario)
    for event in events:
        _update_setting_counter(counters, event)
    return _setting_rows_from_counters(scenario, counters)


def _new_setting_counters(
    scenario: Scenario,
) -> dict[tuple[int, int], dict[str, int]]:
    return {
        (alice_setting, bob_setting): {
            "attempts": 0,
            "emitted": 0,
            "bob_transmitted": 0,
            "coincidences": 0,
            "same": 0,
            "different": 0,
        }
        for alice_setting in range(len(scenario.e91.alice_angles_rad))
        for bob_setting in range(len(scenario.e91.bob_angles_rad))
    }


def _update_setting_counter(
    counters: dict[tuple[int, int], dict[str, int]],
    event: Event,
) -> None:
    counter = counters.get(
        (event.tags.get("alice_setting"), event.tags.get("bob_setting")),
    )
    if counter is None:
        return
    counter["attempts"] += 1
    counter["emitted"] += int(event.emitted)
    counter["bob_transmitted"] += int(event.transmitted)
    if not event.detected:
        return
    counter["coincidences"] += 1
    if event.alice_bit is None or event.bob_bit is None:
        return
    if event.alice_bit == event.bob_bit:
        counter["same"] += 1
    else:
        counter["different"] += 1


def _setting_rows_from_counters(
    scenario: Scenario,
    counters: dict[tuple[int, int], dict[str, int]],
) -> list[JSONObject]:
    key_pairs = set(scenario.e91.key_setting_pairs)
    chsh_pairs = {
        (alice, bob) for alice, bob, _coefficient in scenario.e91.chsh_terms
    }

    rows: list[JSONObject] = []
    for alice_setting, alice_angle in enumerate(scenario.e91.alice_angles_rad):
        for bob_setting, bob_angle in enumerate(scenario.e91.bob_angles_rad):
            counter = counters[(alice_setting, bob_setting)]
            rows.append(
                {
                    "setting_pair": setting_pair_label(alice_setting, bob_setting),
                    "alice_setting": alice_setting,
                    "bob_setting": bob_setting,
                    "alice_angle_rad": alice_angle,
                    "bob_angle_rad": bob_angle,
                    "attempts": counter["attempts"],
                    "emitted": counter["emitted"],
                    "bob_transmitted": counter["bob_transmitted"],
                    "coincidences": counter["coincidences"],
                    "same": counter["same"],
                    "different": counter["different"],
                    "correlation": correlation_from_counts(
                        same=counter["same"],
                        different=counter["different"],
                    ),
                    "used_for_key": (alice_setting, bob_setting) in key_pairs,
                    "used_for_chsh": (alice_setting, bob_setting) in chsh_pairs,
                },
            )
    return rows


def _chsh_s_from_rows(
    scenario: Scenario,
    setting_rows: Sequence[JSONObject],
) -> float | None:
    if not scenario.e91.chsh_estimation_enabled:
        return None
    correlations = {
        (row["alice_setting"], row["bob_setting"]): row["correlation"]
        for row in setting_rows
    }
    return chsh_s_from_correlations(correlations, scenario.e91.chsh_terms)
