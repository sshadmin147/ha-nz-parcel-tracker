"""Diagnostics support for the NZ Parcel Tracker integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ParcelTrackerConfigEntry
from .carriers import CARRIERS

# Diagnostics are pasted into public issues, so redact anything that
# identifies a person, an address or a specific parcel. Over-redacting is
# cheap; under-redacting leaks a user's home address into a GitHub thread.
#
# The shared parcel fields are listed here; each courier adds the names of its
# own payload fields through ``Carrier.redact_keys``.
_SHARED_TO_REDACT = {
    # shared parcel fields we publish ourselves
    "tracking_code",
    "barcode",
    "sender",
    "receiver",
    "url",
    # generic personal data that may appear in any courier's payload
    "recipient",
    "deliveryAddress",
    "address",
    "postalCode",
    "postal_code",
    "city",
    "street",
    "email",
    "name",
    "driver",
    "signature",
}
TO_REDACT = _SHARED_TO_REDACT.union(
    *(carrier.redact_keys for carrier in CARRIERS.values())
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ParcelTrackerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the config entry."""
    coordinator = entry.runtime_data.coordinator

    return {
        "entry_options": async_redact_data(dict(entry.options), TO_REDACT),
        "counts": {
            "incoming_active": len(coordinator.data or []),
            "delivered": len(coordinator.delivered or []),
            "skipped_from_fetch": len(coordinator.delivered_codes),
        },
        "polling": {
            "tier_minutes": coordinator.current_tier_minutes,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            "suspended": coordinator.update_interval is None,
        },
        "incoming": async_redact_data(coordinator.data or [], TO_REDACT),
        "delivered": async_redact_data(coordinator.delivered or [], TO_REDACT),
    }
