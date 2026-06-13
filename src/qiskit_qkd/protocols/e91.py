"""Entanglement-based E91 protocol runner backed by Qiskit circuits."""

from __future__ import annotations

import random
from collections.abc import Sequence
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
from qiskit_qkd.config import Scenario
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
from qiskit_qkd.timing import assign_timing


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
    ) -> SimulationResult:
        if scenario.protocol.name.lower() != "e91":
            raise ValueError("E91Protocol requires scenario.protocol.name='e91'")
        if scenario.source.kind.lower() not in {"entangled_pair", "bell_pair", "e91"}:
            raise ValueError("E91Protocol requires an entangled-pair source")
        if scenario.eavesdropper.kind != "none":
            raise ValueError(
                "E91Protocol has no eavesdropper models; "
                "set eavesdropper kind to 'none' or use BB84Protocol",
            )
        if scenario.dynamic.parameter_schedules:
            raise ValueError(
                "E91Protocol.run does not resolve dynamic schedules; "
                "resolve the scenario first with temporal.scenario_at",
            )

        backend = backend or backend_from_scenario(scenario)
        if hasattr(backend, "configure_from_scenario"):
            backend.configure_from_scenario(scenario)
        rng = make_rng(scenario.seed)
        source = source_from_config(scenario.source)
        channel = channel_from_config(scenario.channel)
        alice_detector = detector_from_config(scenario.detector)
        bob_detector = detector_from_config(scenario.detector)

        prepared = [
            self._prepare_round(
                index=index,
                scenario=scenario,
                source=source,
                channel=channel,
                rng=rng,
            )
            for index in range(scenario.pulses)
        ]
        measured_pairs = self._measure_emitted_pairs(
            backend,
            scenario,
            prepared,
        )
        events = self._resolve_events(
            scenario=scenario,
            prepared=prepared,
            measured_pairs=measured_pairs,
            alice_detector=alice_detector,
            bob_detector=bob_detector,
            rng=rng,
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
        classical = {
            "protocol": "E91",
            "coincidences": metrics.detected,
            "sifted_key_length": metrics.sifted,
            "errors": metrics.errors,
            "qber": metrics.qber,
            "secret_rate_model": "pedagogical_bb84_asymptotic_qber_fraction",
            "chsh_s": metrics.chsh_s,
            "bell_violation": bell["bell_violation"],
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

    @staticmethod
    def _prepare_round(
        *,
        index: int,
        scenario: Scenario,
        source: Any,
        channel: Any,
        rng: random.Random,
    ) -> PreparedE91Round:
        slot_period_s = 1.0 / scenario.clock_rate_hz
        emission_time_s = index * slot_period_s
        emission = source.emit(rng=rng, time_s=emission_time_s)
        bob_transmitted = (
            emission.emitted
            and _sample_single_photon_survival(channel=channel, rng=rng)
        )
        effective_timing = replace(
            scenario.timing,
            jitter_std_s=effective_jitter_std_s(scenario),
        )
        timing = assign_timing(
            time_slot=index,
            pulses=scenario.pulses,
            clock_rate_hz=scenario.clock_rate_hz,
            gate_width_s=scenario.detector.gate_width_s,
            timing=effective_timing,
            transmitted=bob_transmitted,
            rng=rng,
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
        circuit_rounds = [
            (
                round_.alice_angle_rad,
                round_.bob_angle_rad,
                scenario.e91.bell_state,
            )
            for round_ in prepared
            if round_.emitted
        ]
        measured = (
            backend.measure_e91_batch(circuit_rounds)
            if circuit_rounds
            else ()
        )
        if len(measured) != len(circuit_rounds):
            raise ValueError("backend returned a different number of E91 results")
        measured_by_index: dict[int, tuple[int, int]] = {}
        measured_iter = iter(measured)
        for round_ in prepared:
            if round_.emitted:
                measured_by_index[round_.index] = next(measured_iter)
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
    ) -> list[Event]:
        events: list[Event] = []
        alice_background_rate_hz = 0.0
        bob_background_rate_hz = effective_background_count_rate_hz(scenario.channel)
        key_pairs = set(scenario.e91.key_setting_pairs)
        for round_ in prepared:
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
        return Metrics(
            pulses=scenario.pulses,
            emitted=emitted,
            transmitted=transmitted,
            detected=detected,
            sifted=sifted,
            errors=errors,
            qber=qber_value,
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
        return {
            "protocol": "E91",
            "bell_state": scenario.e91.bell_state,
            "chsh_enabled": scenario.e91.chsh_estimation_enabled,
            "chsh_s": chsh_s,
            "bell_violation": chsh_s is not None and chsh_s > 2.0,
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
    key_pairs = set(scenario.e91.key_setting_pairs)
    chsh_pairs = {
        (alice, bob) for alice, bob, _coefficient in scenario.e91.chsh_terms
    }
    counters: dict[tuple[int, int], dict[str, int]] = {
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
    for event in events:
        counter = counters.get(
            (event.tags.get("alice_setting"), event.tags.get("bob_setting")),
        )
        if counter is None:
            continue
        counter["attempts"] += 1
        counter["emitted"] += int(event.emitted)
        counter["bob_transmitted"] += int(event.transmitted)
        if not event.detected:
            continue
        counter["coincidences"] += 1
        if event.alice_bit is None or event.bob_bit is None:
            continue
        if event.alice_bit == event.bob_bit:
            counter["same"] += 1
        else:
            counter["different"] += 1

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
