"""DHL status mapping and payload normalisation.

Pure functions only. Built against DHL's published API description and the
ha-dhl project, not against a captured NZ parcel: the status is the five-value
``statusCode`` baseline. DHL's finer ``status`` text is kept as ``raw_status``
but not interpreted until real parcels show what each text means.
"""

from __future__ import annotations

from typing import Any

from ...const import ParcelStatus
from ...parcels import build_parcel, finalize_history, parse_iso, warn_unmapped_status

CARRIER_NAME = "DHL"

_STATUS_CODES: dict[str, ParcelStatus] = {
    "pre-transit": ParcelStatus.REGISTERED,
    "transit": ParcelStatus.IN_TRANSIT,
    "delivered": ParcelStatus.DELIVERED,
    "failure": ParcelStatus.PROBLEM,
    "unknown": ParcelStatus.UNKNOWN,
}

_KG_PER_UNIT = {
    "kg": 1.0,
    "g": 0.001,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "oz": 0.028349523125,
}


def map_status_code(code: Any) -> ParcelStatus:
    """Map DHL's ``statusCode`` to a :class:`ParcelStatus`; unknown codes warn once."""
    if not isinstance(code, str) or not code:
        return ParcelStatus.UNKNOWN
    mapped = _STATUS_CODES.get(code)
    if mapped is not None:
        return mapped
    warn_unmapped_status(CARRIER_NAME, code)
    return ParcelStatus.UNKNOWN


def _weight_kg(details: Any) -> float | None:
    weight = details.get("weight") if isinstance(details, dict) else None
    if not isinstance(weight, dict):
        return None
    value = weight.get("value")
    factor = _KG_PER_UNIT.get(str(weight.get("unitText") or "").strip().lower())
    if factor is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return round(value * factor, 3)


def sanitize_shipment(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep only the fields normalisation needs; never cache addresses."""
    status = raw.get("status") if isinstance(raw.get("status"), dict) else {}
    frame = raw.get("estimatedDeliveryTimeFrame")
    frame = frame if isinstance(frame, dict) else {}
    details = raw.get("details") if isinstance(raw.get("details"), dict) else {}
    weight = details.get("weight") if isinstance(details.get("weight"), dict) else None
    return {
        "tracking_code": raw.get("tracking_code"),
        "id": raw.get("id"),
        "service": raw.get("service"),
        "status": {
            "statusCode": status.get("statusCode"),
            "status": status.get("status"),
            "timestamp": status.get("timestamp"),
        },
        "estimatedTimeOfDelivery": raw.get("estimatedTimeOfDelivery"),
        "estimatedDeliveryTimeFrame": {
            "estimatedFrom": frame.get("estimatedFrom"),
            "estimatedThrough": frame.get("estimatedThrough"),
        },
        "details": {
            "weight": {
                "value": weight.get("value"),
                "unitText": weight.get("unitText"),
            }
            if weight
            else None
        },
        "events": [
            {
                "timestamp": event.get("timestamp"),
                "statusCode": event.get("statusCode"),
                "status": event.get("status"),
            }
            for event in raw.get("events") or []
            if isinstance(event, dict)
        ],
    }


def normalize_parcel(
    raw: dict[str, Any], *, include_history: bool = False
) -> dict[str, Any]:
    """Return the shared parcel dict; ``raw`` holds the sanitised shipment."""
    raw = sanitize_shipment(raw)
    status_obj = raw["status"]
    status = map_status_code(status_obj["statusCode"])
    delivered = status is ParcelStatus.DELIVERED
    events = sorted(
        raw["events"],
        key=lambda event: (
            parse_iso(event.get("timestamp")) or parse_iso("0001-01-01T00:00:00+00:00")
        ),
    )

    delivered_at = None
    if delivered:
        delivered_at = next(
            (
                event["timestamp"]
                for event in reversed(events)
                if event.get("statusCode") == "delivered"
            ),
            status_obj["timestamp"],
        )

    planned_from = planned_to = None
    if not delivered:
        frame = raw["estimatedDeliveryTimeFrame"]
        if frame["estimatedFrom"] or frame["estimatedThrough"]:
            planned_from, planned_to = frame["estimatedFrom"], frame["estimatedThrough"]
        elif raw["estimatedTimeOfDelivery"]:
            planned_from = planned_to = raw["estimatedTimeOfDelivery"]

    history = None
    if include_history:
        history = finalize_history(
            [
                {
                    "timestamp": event["timestamp"],
                    "status": map_status_code(event.get("statusCode")),
                    "raw_status": event.get("status"),
                }
                for event in events
                if event.get("timestamp")
            ]
        )

    return build_parcel(
        carrier=CARRIER_NAME,
        # The number the user entered, not DHL's own id: services, sensors and
        # the options form all key on it.
        barcode=raw["tracking_code"],
        status=status,
        raw_status=status_obj["status"],
        delivered=delivered,
        delivered_at=delivered_at,
        planned_from=planned_from,
        planned_to=planned_to,
        weight=_weight_kg(raw["details"]),
        history=history,
        raw=raw,
    )
