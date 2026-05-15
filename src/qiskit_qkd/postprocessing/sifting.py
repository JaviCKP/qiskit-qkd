"""Classical sifting rules for prepare-and-measure QKD events."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from qiskit_qkd.results import Event


def sift_bb84_event(event: Event) -> Event:
    """Mark one BB84 event as sifted when Alice and Bob used the same basis."""

    assigned_to_event_slot = (
        event.assigned_slot is None or event.assigned_slot == event.time_slot
    )
    sifted = (
        event.detected
        and assigned_to_event_slot
        and event.alice_basis is not None
        and event.alice_basis == event.bob_basis
    )
    error = None
    if sifted:
        error = event.bob_bit != event.alice_bit
    return replace(event, sifted=sifted, error=error)


def sift_bb84_events(events: Iterable[Event]) -> tuple[Event, ...]:
    """Mark BB84 events as sifted when Alice and Bob used the same basis."""

    return tuple(sift_bb84_event(event) for event in events)
