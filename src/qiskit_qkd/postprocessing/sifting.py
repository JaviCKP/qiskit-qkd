"""Classical sifting rules for prepare-and-measure QKD events."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from qiskit_qkd.results import Event


def sift_bb84_event(event: Event, *, sifting_enabled: bool = True) -> Event:
    """Mark one BB84 event as sifted when Alice and Bob used the same basis.

    With ``sifting_enabled=False`` the basis comparison is skipped and every
    valid detection becomes a key candidate, so mismatched-basis rounds
    contribute random bits (about 25% QBER in two-basis BB84).
    """

    assigned_to_event_slot = (
        event.assigned_slot is None or event.assigned_slot == event.time_slot
    )
    bases_match = (
        not sifting_enabled
        or (
            event.alice_basis is not None
            and event.alice_basis == event.bob_basis
        )
    )
    sifted = event.detected and assigned_to_event_slot and bases_match
    error = None
    if sifted:
        error = event.bob_bit != event.alice_bit
    return replace(event, sifted=sifted, error=error)


def sift_bb84_events(
    events: Iterable[Event],
    *,
    sifting_enabled: bool = True,
) -> tuple[Event, ...]:
    """Mark BB84 events as sifted when Alice and Bob used the same basis."""

    return tuple(
        sift_bb84_event(event, sifting_enabled=sifting_enabled)
        for event in events
    )
