"""Status mapping and payload normalisation for the Freightways tracking pages.

Pure functions only: no I/O and no Home Assistant objects.
"""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
import re
from typing import Any

from ...const import ParcelStatus
from ...parcels import build_parcel, finalize_history, parse_iso, warn_unmapped_status

# Keyed by the title of each travel-history entry. "On Board" is the scan that
# puts the parcel on the delivery courier's vehicle (seen the same day as the
# delivery). Anything not listed surfaces as ``unknown`` plus a one-shot warning.
_STATUS_MAP: dict[str, ParcelStatus] = {
    "Pickup": ParcelStatus.IN_TRANSIT,
    "On Board": ParcelStatus.OUT_FOR_DELIVERY,
    "Delivery": ParcelStatus.DELIVERED,
}

# Informational entries that do not move the parcel, for example ``Status``
# ("Item has been re-ticketed"). They stay in the history with no status and
# never decide the parcel's current status.
_INFORMATIONAL: frozenset[str] = frozenset({"Status"})

_TIME_FORMAT = "%I:%M%p %d/%m/%Y"
_CODE_RE = re.compile(r"([A-Z0-9]{3,8})[ -]+([A-Z0-9]{6,12})")
_EPOCH = datetime.min.replace(tzinfo=UTC)


def map_parcel_status(carrier_name: str, title: str | None) -> ParcelStatus:
    """Map an event title to a :class:`ParcelStatus`; unknown titles warn once."""
    if not title:
        return ParcelStatus.UNKNOWN
    mapped = _STATUS_MAP.get(title)
    if mapped is not None:
        return mapped
    if title not in _INFORMATIONAL:
        warn_unmapped_status(carrier_name, title)
    return ParcelStatus.UNKNOWN


def map_event_status(carrier_name: str, title: str | None) -> ParcelStatus | None:
    """Map a history entry's title to a status, or ``None`` when unmapped."""
    if not title:
        return None
    mapped = _STATUS_MAP.get(title)
    if mapped is not None:
        return mapped
    if title not in _INFORMATIONAL:
        warn_unmapped_status(carrier_name, title)
    return None


def split_code(code: str) -> tuple[str, str] | None:
    """Split ``<customer number> <consignment id>`` (space or hyphen), or ``None``."""
    match = _CODE_RE.fullmatch(code.upper().strip())
    return (match[1], match[2]) if match else None


def to_iso(value: Any, zone: tzinfo | None) -> str | None:
    """Turn ``11:34AM 24/8/2026`` (local time) into an ISO 8601 string, or ``None``."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value.strip().upper(), _TIME_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=zone or UTC).isoformat()


def tracking_url(base_url: str, code: str | None) -> str | None:
    """Return the public tracking page for ``code``, or ``None``."""
    parts = split_code(code or "")
    if parts is None:
        return None
    customer, consignment = parts
    return (
        f"{base_url}?page=1&Key_Type=CustomerLabel&VCCA=Enabled"
        f"&customer_number={customer}&consignment_id={consignment}"
    )


def sanitize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only each event's title and time, plus the code we asked for."""
    return {
        "tracking_code": raw.get("tracking_code"),
        "events": [
            {"title": event.get("title"), "time": event.get("time")}
            for event in raw.get("events", [])
            if isinstance(event, dict)
        ],
    }


def build_history(
    carrier_name: str, events: list[dict[str, Any]], zone: tzinfo | None
) -> list[dict[str, Any]]:
    """Build the ``history`` list; ``raw_status`` is the event title."""
    entries = []
    for event in events:
        timestamp = to_iso(event.get("time"), zone)
        if timestamp:
            entries.append(
                {
                    "timestamp": timestamp,
                    "status": map_event_status(carrier_name, event.get("title")),
                    "raw_status": event.get("title"),
                }
            )
    return finalize_history(entries)


def normalize_parcel(
    raw: dict[str, Any],
    *,
    carrier_name: str,
    base_url: str,
    include_history: bool = False,
    zone: tzinfo | None = None,
) -> dict[str, Any]:
    """Return the shared parcel dict; ``raw`` keeps only titles and times.

    The parcel's status is that of its newest event that is not purely
    informational, so a parcel that was delivered, picked up again and
    delivered once more reads as delivered at the last delivery.
    """
    raw = sanitize_payload(raw)
    events = raw["events"]
    dated = [
        (parse_iso(to_iso(event["time"], zone)) or _EPOCH, index, event)
        for index, event in enumerate(events)
        if event.get("title") not in _INFORMATIONAL
    ]
    dated.sort(key=lambda item: (item[0], item[1]))
    newest = dated[-1][2] if dated else {}
    title = newest.get("title")
    status = map_parcel_status(carrier_name, title)
    delivered = status is ParcelStatus.DELIVERED
    code = raw.get("tracking_code")

    return build_parcel(
        carrier=carrier_name,
        barcode=code,
        status=status,
        raw_status=title,
        delivered=delivered,
        delivered_at=to_iso(newest.get("time"), zone) if delivered else None,
        url=tracking_url(base_url, code),
        history=build_history(carrier_name, events, zone) if include_history else None,
        raw={"events": events},
    )
