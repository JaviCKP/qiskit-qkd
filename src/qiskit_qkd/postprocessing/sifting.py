"""Classical sifting rules for prepare-and-measure QKD events."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from qiskit_qkd.results import Event


def bb84_sift_outcome(
    *,
    detected: bool,
    assigned_slot: int | None,
    time_slot: int,
    alice_basis: str | None,
    bob_basis: str | None,
    alice_bit: int | None,
    bob_bit: int | None,
    sifting_enabled: bool = True,
) -> tuple[bool, bool | None]:
    """Return BB84 ``(sifted, error)`` metadata before building an event.

    Keeping this calculation separate lets protocol runners construct one
    final :class:`Event` with its classical outcomes already populated.  The
    legacy :func:`sift_bb84_event` wrapper below still returns a replaced event
    for callers that already have an event instance.
    """

    assigned_to_event_slot = assigned_slot is None or assigned_slot == time_slot
    bases_match = (
        not sifting_enabled
        or (
            alice_basis is not None
            and alice_basis == bob_basis
        )
    )
    sifted = detected and assigned_to_event_slot and bases_match
    error = None if not sifted else bob_bit != alice_bit
    return sifted, error


def sift_bb84_event(event: Event, *, sifting_enabled: bool = True) -> Event:
    """Mark one BB84 event as sifted when Alice and Bob used the same basis.

    With ``sifting_enabled=False`` the basis comparison is skipped and every
    valid detection becomes a key candidate, so mismatched-basis rounds
    contribute random bits (about 25% QBER in two-basis BB84).
    """

    sifted, error = bb84_sift_outcome(
        detected=event.detected,
        assigned_slot=event.assigned_slot,
        time_slot=event.time_slot,
        alice_basis=event.alice_basis,
        bob_basis=event.bob_basis,
        alice_bit=event.alice_bit,
        bob_bit=event.bob_bit,
        sifting_enabled=sifting_enabled,
    )
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
