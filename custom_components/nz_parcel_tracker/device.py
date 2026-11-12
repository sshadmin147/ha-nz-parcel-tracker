"""The device every entity of this integration belongs to.

One place, because sensors, the button and the calendar must all land on the
*same* device entry. The device is the integration hub, not a courier, so it
stays the same however many couriers are tracked.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

ATTRIBUTION = "Data provided by the couriers' public tracking services"


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the DeviceInfo shared by every entity of this hub."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="NZ Parcel Tracker",
        entry_type=DeviceEntryType.SERVICE,
    )
