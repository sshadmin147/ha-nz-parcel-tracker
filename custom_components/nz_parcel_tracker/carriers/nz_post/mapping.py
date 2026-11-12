"""NZ Post status mapping and payload normalisation.

Pure functions only: no I/O and no Home Assistant objects, so the mapping is
unit-testable without spinning up HA.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...const import ParcelStatus
from ...parcels import (
    build_parcel,
    clean_description,
    finalize_history,
    parse_iso,
    to_iso_timestamp,
    warn_unmapped_status,
)
from .const import TRACKING_URL_BASE

CARRIER_NAME = "NZ Post"

# Keyed by NZ Post's own display text, which every event carries. Ambiguous
# wording is deliberately left out so it falls through to ``unknown`` and the
# one-shot warning: "Handed over" (it follows a failed delivery attempt but
# does not say to whom), and every delivery-attempt/collection code whose text
# has not been seen on a real parcel.
_STATUS_MAP: dict[str, ParcelStatus] = {
    "Tracking number allocated to parcel": ParcelStatus.REGISTERED,
    "Shipment data submitted": ParcelStatus.REGISTERED,
    "Label created": ParcelStatus.REGISTERED,
    "Parcel pickup request received": ParcelStatus.REGISTERED,
    "Parcel pickup request allocated to driver": ParcelStatus.REGISTERED,
    "Collected from sender": ParcelStatus.IN_TRANSIT,
    "Picked up/Collected": ParcelStatus.IN_TRANSIT,
    "Handover to airline": ParcelStatus.IN_TRANSIT,
    "International departure": ParcelStatus.IN_TRANSIT,
    "Flight arrival": ParcelStatus.IN_TRANSIT,
    "International arrival": ParcelStatus.IN_TRANSIT,
    "Handover for arrival processing": ParcelStatus.IN_TRANSIT,
    "With border agency": ParcelStatus.IN_TRANSIT,
    "Held for clearance": ParcelStatus.IN_TRANSIT,
    "Released for delivery": ParcelStatus.IN_TRANSIT,
    "Cleared for import": ParcelStatus.IN_TRANSIT,
    "Arrival at sort depot": ParcelStatus.IN_TRANSIT,
    "Arrival at sorting centre": ParcelStatus.IN_TRANSIT,
    # "handed over and will be ready for collection soon" — on its way to a
    # pickup point, not collectable yet, so deliberately not at_pickup_point.
    "Handed over": ParcelStatus.IN_TRANSIT,
    "Processing at international depot": ParcelStatus.IN_TRANSIT,
    "Processed at depot": ParcelStatus.IN_TRANSIT,
    "Processed at outbound depot": ParcelStatus.IN_TRANSIT,
    "Processed at facility": ParcelStatus.IN_TRANSIT,
    "At local/regional depot": ParcelStatus.IN_TRANSIT,
    "In transit with airline": ParcelStatus.IN_TRANSIT,
    "In transit to local depot": ParcelStatus.IN_TRANSIT,
    "Ready for courier": ParcelStatus.IN_TRANSIT,
    "With courier for delivery": ParcelStatus.OUT_FOR_DELIVERY,
    "Delayed": ParcelStatus.PROBLEM,
    "Delivery attempted - refer to card": ParcelStatus.PROBLEM,
    "Delivered": ParcelStatus.DELIVERED,
}

# Fallback for an event that arrives without display text. Only codes whose
# NZ Post wording is known are listed.
_EDIFACT_STATUS_MAP: dict[str, ParcelStatus] = {
    "997": ParcelStatus.REGISTERED,
    "205": ParcelStatus.REGISTERED,
    "206": ParcelStatus.REGISTERED,
    "5303": ParcelStatus.REGISTERED,
    "6908": ParcelStatus.REGISTERED,
    "13": ParcelStatus.IN_TRANSIT,
    "144": ParcelStatus.IN_TRANSIT,  # pairs with "Handed over"
    "5000": ParcelStatus.IN_TRANSIT,
    "8": ParcelStatus.IN_TRANSIT,
    "58": ParcelStatus.IN_TRANSIT,
    "591": ParcelStatus.IN_TRANSIT,
    "595": ParcelStatus.IN_TRANSIT,
    "6028": ParcelStatus.IN_TRANSIT,
    "5007": ParcelStatus.IN_TRANSIT,
    "6025": ParcelStatus.IN_TRANSIT,
    "5015": ParcelStatus.IN_TRANSIT,
    "5016": ParcelStatus.IN_TRANSIT,
    "5019": ParcelStatus.IN_TRANSIT,
    "5023": ParcelStatus.IN_TRANSIT,
    "5017": ParcelStatus.IN_TRANSIT,
    "5360": ParcelStatus.IN_TRANSIT,
    "5020": ParcelStatus.IN_TRANSIT,
    "5041": ParcelStatus.IN_TRANSIT,
    "5042": ParcelStatus.IN_TRANSIT,
    "5064": ParcelStatus.IN_TRANSIT,
    "5280": ParcelStatus.IN_TRANSIT,
    "5282": ParcelStatus.IN_TRANSIT,
    "5283": ParcelStatus.IN_TRANSIT,
    "5284": ParcelStatus.IN_TRANSIT,
    "5285": ParcelStatus.IN_TRANSIT,
    "5292": ParcelStatus.IN_TRANSIT,
    "6069": ParcelStatus.IN_TRANSIT,
    "6068": ParcelStatus.IN_TRANSIT,
    "6063": ParcelStatus.IN_TRANSIT,
    "6049": ParcelStatus.IN_TRANSIT,
    "6054": ParcelStatus.IN_TRANSIT,
    "6071": ParcelStatus.IN_TRANSIT,
    "5199": ParcelStatus.IN_TRANSIT,
    "5213": ParcelStatus.IN_TRANSIT,
    "32": ParcelStatus.OUT_FOR_DELIVERY,
    "5045": ParcelStatus.OUT_FOR_DELIVERY,
    "40": ParcelStatus.PROBLEM,
    "52": ParcelStatus.PROBLEM,
    "22": ParcelStatus.DELIVERED,
    "5022": ParcelStatus.DELIVERED,
}


def map_parcel_status(code: str | None) -> ParcelStatus:
    """Map a NZ Post status text or code to a :class:`ParcelStatus`.

    ``None`` (a not-yet-scanned parcel) reports ``unknown`` silently; an
    unrecognised code reports ``unknown`` with a one-shot warning.
    """
    if not code:
        return ParcelStatus.UNKNOWN
    mapped = _STATUS_MAP.get(code) or _EDIFACT_STATUS_MAP.get(code)
    if mapped is not None:
        return mapped
    warn_unmapped_status(CARRIER_NAME, code)
    return ParcelStatus.UNKNOWN


def map_event_status(code: str | None) -> ParcelStatus | None:
    """Map a history entry's status text or code to a status, or ``None``.

    Unmapped codes keep ``status: null`` on the history entry (rather than
    ``unknown``, so a consumer can tell "no mapping" from "mapped to unknown")
    and warn once, reusing the parcel-status one-shot set.
    """
    if not code:
        return None
    mapped = _STATUS_MAP.get(code) or _EDIFACT_STATUS_MAP.get(code)
    if mapped is not None:
        return mapped
    warn_unmapped_status(CARRIER_NAME, code)
    return None


def build_history(events: list | None, *, max_events: int | None = None) -> list[dict]:
    """Build the ``history`` list from NZ Post's event timeline.

    Each entry is ``{timestamp, status, raw_status}``; ``raw_status`` is NZ
    Post's own text, or its event code when there is no text. Sorting and
    capping is done by :func:`finalize_history`.
    """
    entries: list[dict] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        timestamp = to_iso_timestamp(event.get("date_time"))
        if not timestamp:
            continue
        entries.append(
            {
                "timestamp": timestamp,
                "status": map_event_status(
                    event.get("status") or event.get("edifact_code")
                ),
                "raw_status": event.get("status") or event.get("edifact_code"),
            }
        )
    if max_events is None:
        return finalize_history(entries)
    return finalize_history(entries, max_events=max_events)


def tracking_url(tracking_code: str | None) -> str | None:
    """Return the confirmed per-parcel deep link on NZ Post's public tracker."""
    if not tracking_code:
        return None
    return f"{TRACKING_URL_BASE}?trackid={tracking_code}"


def sanitize_raw_parcel(raw: dict) -> dict:
    """Keep only the payload fields safe to retain between polls."""
    return {
        "tracking_reference": raw.get("tracking_reference"),
        "tracking_events": [
            {
                "date_time": to_iso_timestamp(event.get("date_time")),
                "status": event.get("status"),
                "edifact_code": event.get("edifact_code"),
                "description": clean_description(event.get("description")),
            }
            for event in raw.get("tracking_events", [])
            if isinstance(event, dict)
        ],
    }


def normalize_parcel(raw: dict, *, include_history: bool = False) -> dict:
    """Return the shared parcel dict with the payload under ``raw``.

    The public payload only confirms a code and a timeline. Location, signer
    and the original full timeline are deliberately excluded from ``raw``.
    """
    tracking_code = raw.get("tracking_reference")
    events = [
        event for event in raw.get("tracking_events", []) if isinstance(event, dict)
    ]
    events.sort(
        key=lambda event: (
            parse_iso(to_iso_timestamp(event.get("date_time")))
            or datetime.max.replace(tzinfo=UTC)
        )
    )
    newest = events[-1] if events else {}
    status_code = newest.get("status") or newest.get("edifact_code")
    status = map_parcel_status(status_code)
    delivered = status is ParcelStatus.DELIVERED
    delivered_event = next(
        (
            event
            for event in reversed(events)
            if map_parcel_status(event.get("status") or event.get("edifact_code"))
            is ParcelStatus.DELIVERED
        ),
        None,
    )
    safe_events = sanitize_raw_parcel(raw)["tracking_events"]

    return build_parcel(
        carrier=CARRIER_NAME,
        barcode=tracking_code,
        status=status,
        raw_status=status_code,
        delivered=delivered,
        delivered_at=to_iso_timestamp(delivered_event.get("date_time"))
        if delivered_event
        else None,
        url=tracking_url(tracking_code),
        history=build_history(events) if include_history else None,
        raw={"tracking_events": safe_events},
    )
