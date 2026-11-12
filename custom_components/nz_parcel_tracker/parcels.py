"""Courier-independent parcel helpers.

Everything in this module is a **pure function**: no I/O and no Home Assistant
objects beyond the config entry's options. A courier's own mapping lives in its
package under ``carriers/``; it builds its parcels with :func:`build_parcel` so
every courier publishes exactly the same set of keys.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import unescape
import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    DEFAULT_DELIVERED_FILTER_AMOUNT,
    DEFAULT_DELIVERED_FILTER_TYPE,
    HISTORY_MAX_EVENTS,
    ParcelStatus,
)

_LOGGER = logging.getLogger(__name__)

# Where users report a status we do not map yet; points at this repo so the
# logged line can be pasted straight into a new issue.
NEW_ISSUE_URL = "https://github.com/sshadmin147/ha-nz-parcel-tracker/issues/new"

# Status codes we have already warned about, so each unmapped one is logged
# only once per HA session instead of on every poll.
_unmapped_statuses_logged: set[str] = set()


def warn_unmapped_status(carrier_name: str, code: str) -> None:
    """Log an unmapped courier status once, with a copy-paste issue link."""
    key = f"{carrier_name}:{code}"
    if key in _unmapped_statuses_logged:
        return
    _unmapped_statuses_logged.add(key)
    _LOGGER.warning(
        "Unrecognised %s status — help us map it. Open an issue "
        "and paste this line: %s\n  status=%s → reported as 'unknown'",
        carrier_name,
        NEW_ISSUE_URL,
        code,
    )


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string to an aware datetime, or ``None`` on failure.

    Naive values are treated as UTC so a list always sorts without crashing on
    a mixed set.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def to_iso_timestamp(value: Any) -> str | None:
    """Return an ISO 8601 string for an API timestamp field.

    Numbers are treated as **epoch milliseconds**. Strings pass through
    untouched; their consumers are guarded by :func:`parse_iso`. Convert before
    calling if a courier stamps in seconds.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return str(value)


def format_dimensions(
    length: float | None, width: float | None, height: float | None
) -> dict[str, Any] | None:
    """Return the ``dimensions`` dict, or ``None`` when incomplete.

    Units contract: **centimetres**, with ``text`` pre-formatted as
    ``"L x W x H cm"`` (integer values, lowercase ``x``) so dashboards can show
    a dimension without doing their own formatting. Convert before calling if
    the courier reports millimetres or inches.
    """
    if length is None or width is None or height is None:
        return None
    return {
        "length": length,
        "width": width,
        "height": height,
        "text": f"{round(length)} x {round(width)} x {round(height)} cm",
    }


def clean_description(value: Any) -> str | None:
    """Remove markup, entities and control characters from event text."""
    if value is None:
        return None
    cleaned = re.sub(r"<[^>]*>", "", unescape(str(value)))
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", cleaned)
    return " ".join(cleaned.split()) or None


def finalize_history(
    entries: list[dict], *, max_events: int = HISTORY_MAX_EVENTS
) -> list[dict]:
    """Sort and cap a courier's history entries.

    Each entry is ``{timestamp, status, raw_status}``, kept top-level (not
    under ``raw``). Sorted oldest to newest, entries whose timestamp cannot be
    parsed go last, and only the most recent ``max_events`` are kept.
    """
    parseable: list[tuple[datetime, dict]] = []
    unparseable: list[dict] = []
    for entry in entries:
        parsed = parse_iso(entry.get("timestamp"))
        if parsed is None:
            unparseable.append(entry)
        else:
            parseable.append((parsed, entry))
    parseable.sort(key=lambda item: item[0])
    ordered = [entry for _, entry in parseable] + unparseable
    return ordered[-max_events:]


def build_parcel(
    *,
    carrier: str,
    barcode: str | None,
    status: ParcelStatus,
    raw_status: str | None,
    delivered: bool,
    delivered_at: str | None = None,
    sender: str | None = None,
    receiver: str | None = None,
    planned_from: str | None = None,
    planned_to: str | None = None,
    pickup: bool = False,
    pickup_point: str | None = None,
    url: str | None = None,
    weight: float | None = None,
    dimensions: dict[str, Any] | None = None,
    history: list[dict] | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a parcel with exactly the keys every courier publishes.

    A field a courier cannot provide stays ``None`` (never omitted), so
    automations and dashboards can rely on the shape. The key order is part of
    the contract.
    """
    return {
        "carrier": carrier,
        "barcode": barcode,
        "sender": sender,
        "receiver": receiver,
        "status": status,
        "raw_status": raw_status,
        "delivered": delivered,
        "delivered_at": delivered_at,
        "planned_from": planned_from,
        "planned_to": planned_to,
        "pickup": pickup,
        "pickup_point": pickup_point,
        "url": url,
        "weight": weight,
        "dimensions": dimensions,
        "history": history,
        "raw": raw if raw is not None else {},
    }


def sort_parcels_by_ts(
    parcels: list[dict], key_field: str, *, descending: bool = False
) -> list[dict]:
    """Return normalised parcels sorted by the ISO timestamp at ``key_field``.

    Sort order: incoming/outgoing ascending on ``planned_from``,
    delivered descending on ``delivered_at``. Parcels whose value is missing or
    unparseable always sort to the end, regardless of ``descending``.
    """
    with_ts: list[tuple[datetime, dict]] = []
    without_ts: list[dict] = []
    for parcel in parcels:
        parsed = parse_iso(parcel.get(key_field))
        if parsed is None:
            without_ts.append(parcel)
        else:
            with_ts.append((parsed, parcel))
    with_ts.sort(key=lambda item: item[0], reverse=descending)
    return [parcel for _, parcel in with_ts] + without_ts


def apply_delivered_filter(parcels: list[dict], entry: ConfigEntry) -> list[dict]:
    """Trim the delivered list per the entry's retention option.

    ``parcels`` must already be sorted newest-first. ``days`` keeps deliveries
    from the last N days (an unparseable ``delivered_at`` is kept rather than
    silently dropped); the ``parcels`` type keeps the N most recent. Parcels
    stay *tracked* either way — this only controls what the delivered sensor
    shows.
    """
    options = entry.options
    filter_type = options.get(CONF_DELIVERED_FILTER_TYPE, DEFAULT_DELIVERED_FILTER_TYPE)
    amount = int(
        options.get(CONF_DELIVERED_FILTER_AMOUNT, DEFAULT_DELIVERED_FILTER_AMOUNT)
    )
    if filter_type == "days":
        cutoff = datetime.now(UTC) - timedelta(days=amount)
        return [
            parcel
            for parcel in parcels
            if (parsed := parse_iso(parcel.get("delivered_at"))) is None
            or parsed >= cutoff
        ]
    return parcels[:amount]
