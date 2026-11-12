"""Shared test helpers."""

from __future__ import annotations

from custom_components.nz_parcel_tracker.carriers.nz_post import NZPostCarrier
from custom_components.nz_parcel_tracker.coordinator import ParcelCoordinator


def make_coordinator(hass, client, entry) -> ParcelCoordinator:
    """Build a coordinator whose NZ Post carrier talks to the mocked ``client``."""
    return ParcelCoordinator(hass, {NZPostCarrier.key: NZPostCarrier(client)}, entry)
