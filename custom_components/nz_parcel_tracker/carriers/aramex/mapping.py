"""Aramex status mapping and payload normalisation.

Pure functions only: no I/O and no Home Assistant objects.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, tzinfo
from typing import Any

from ...const import ParcelStatus
from ...parcels import (
    build_parcel,
    finalize_history,
    parse_iso,
    to_iso_timestamp,
    warn_unmapped_status,
)
from .const import TRACKING_URL_BASE

CARRIER_NAME = "Aramex"

# Keyed by the scan codes seen so far. Prefer mapping too little over mapping
# wrongly: an unmapped code surfaces as ``unknown`` plus a one-shot warning.
_STATUS_MAP: dict[str, ParcelStatus] = {
    "PP8": ParcelStatus.REGISTERED,
    **dict.fromkeys(
        ("PPP", "PP1", "PCY", "078", "RIA", "B72", "S2M", "SYD", "TOO", "TRN"),
        ParcelStatus.IN_TRANSIT,
    ),
    "ONB": ParcelStatus.OUT_FOR_DELIVERY,
    "R36": ParcelStatus.DELIVERED,
    "YES": ParcelStatus.DELIVERED,
    "U03": ParcelStatus.PROBLEM,
    "UND": ParcelStatus.PROBLEM,
    "RTS": ParcelStatus.RETURNING,
}

_EPOCH = datetime.min.replace(tzinfo=UTC)


def sanitize_status_text(value: Any) -> str | None:
    """Return display-safe scan text without control characters or excess space."""
    if not isinstance(value, str):
        return None
    cleaned = " ".join(
        "".join(char for char in value if char.isprintable() or char.isspace()).split()
    )
    return cleaned[:200] or None


def sanitize_tracking_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields normalisation needs; never cache recipient data."""
    raw_result = raw.get("result")
    result = raw_result if isinstance(raw_result, dict) else {}
    raw_scans = result.get("Scans")
    scans = raw_scans if isinstance(raw_scans, list) else []
    return {
        "tracking_code": raw.get("tracking_code"),
        "result": {
            "LabelNumber": result.get("LabelNumber"),
            "DeliveryETADate": result.get("DeliveryETADate"),
            "Scans": [
                {
                    "Status": scan.get("Status"),
                    "StatusDescription": sanitize_status_text(
                        scan.get("StatusDescription")
                    ),
                    "RealDateTime": scan.get("RealDateTime"),
                    "Date": scan.get("Date"),
                }
                for scan in scans
                if isinstance(scan, dict)
            ],
        },
    }


def map_parcel_status(code: str | None) -> ParcelStatus:
    """Map a scan code to a :class:`ParcelStatus`.

    ``None`` (a not-yet-scanned parcel) reports ``unknown`` silently; an
    unrecognised code reports ``unknown`` with a one-shot warning.
    """
    if not code:
        return ParcelStatus.UNKNOWN
    mapped = _STATUS_MAP.get(code)
    if mapped is not None:
        return mapped
    warn_unmapped_status(CARRIER_NAME, code)
    return ParcelStatus.UNKNOWN


def map_event_status(code: str | None) -> ParcelStatus | None:
    """Map a history entry's code to a status, or ``None`` when unmapped."""
    if not code:
        return None
    mapped = _STATUS_MAP.get(code)
    if mapped is not None:
        return mapped
    warn_unmapped_status(CARRIER_NAME, code)
    return None


def _scan_timestamp(scan: dict[str, Any]) -> str | None:
    return to_iso_timestamp(scan.get("RealDateTime") or scan.get("Date"))


def build_history(scans: list | None) -> list[dict]:
    """Build the ``history`` list; ``raw_status`` is the scan text or its code."""
    entries: list[dict] = []
    for scan in scans or []:
        if not isinstance(scan, dict):
            continue
        timestamp = _scan_timestamp(scan)
        if not timestamp:
            continue
        entries.append(
            {
                "timestamp": timestamp,
                "status": map_event_status(scan.get("Status")),
                "raw_status": sanitize_status_text(scan.get("StatusDescription"))
                or scan.get("Status"),
            }
        )
    return finalize_history(entries)


def tracking_url(tracking_code: str | None) -> str | None:
    """Return the per-parcel deep link on Aramex's public tracker."""
    if not tracking_code:
        return None
    return f"{TRACKING_URL_BASE}?l={tracking_code}"


def _parse_eta_date(value: Any) -> date | None:
    """Parse ``DeliveryETADate`` (``DD/MM/YYYY``), or ``None``.

    This is Aramex's estimate at booking time and is not recomputed as the
    parcel moves, so a delayed parcel can carry a date already in the past.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def eta_window(value: Any, zone: tzinfo | None) -> tuple[str | None, str | None]:
    """Return ``(planned_from, planned_to)`` as an all-day window in ``zone``."""
    eta_date = _parse_eta_date(value)
    if eta_date is None:
        return None, None
    tz = zone or UTC
    return (
        datetime.combine(eta_date, time.min, tz).isoformat(),
        datetime.combine(eta_date, time.max, tz).isoformat(),
    )


def normalize_parcel(
    raw: dict[str, Any],
    *,
    include_history: bool = False,
    zone: tzinfo | None = None,
) -> dict[str, Any]:
    """Return the shared parcel dict; only code, text and time are kept in ``raw``."""
    raw = sanitize_tracking_payload(raw)
    result = raw["result"]
    scans = result["Scans"]
    newest = max(
        scans,
        key=lambda scan: parse_iso(_scan_timestamp(scan)) or _EPOCH,
        default={},
    )
    tracking_code = result.get("LabelNumber") or raw.get("tracking_code")
    status_code = newest.get("Status")
    status = map_parcel_status(status_code)
    delivered = status is ParcelStatus.DELIVERED
    timestamp = _scan_timestamp(newest) if newest else None
    text = sanitize_status_text(newest.get("StatusDescription"))
    planned_from, planned_to = (
        (None, None) if delivered else eta_window(result.get("DeliveryETADate"), zone)
    )

    return build_parcel(
        carrier=CARRIER_NAME,
        barcode=tracking_code,
        status=status,
        raw_status=text or status_code,
        delivered=delivered,
        delivered_at=timestamp if delivered else None,
        planned_from=planned_from,
        planned_to=planned_to,
        url=tracking_url(tracking_code),
        history=build_history(scans) if include_history else None,
        raw={"status": status_code, "status_text": text, "timestamp": timestamp},
    )
