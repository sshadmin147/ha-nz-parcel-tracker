"""Registry of the couriers this integration can track.

Adding a courier means adding its class to :data:`CARRIERS`; see
:mod:`.base` for the interface and the steps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp

from .aramex import AramexCarrier
from .base import Carrier, CarrierApiError
from .dhl import DHLCarrier
from .nz_couriers import NZCouriersCarrier
from .nz_post import NZPostCarrier
from .post_haste import PostHasteCarrier

__all__ = [
    "CARRIERS",
    "Carrier",
    "CarrierApiError",
    "available_carriers",
    "create_carriers",
]

#: Every supported courier by key. The user always picks the courier for a
#: parcel (codes are never guessed), so the order only affects the selector.
CARRIERS: dict[str, type[Carrier]] = {
    AramexCarrier.key: AramexCarrier,
    DHLCarrier.key: DHLCarrier,
    NZCouriersCarrier.key: NZCouriersCarrier,
    NZPostCarrier.key: NZPostCarrier,
    PostHasteCarrier.key: PostHasteCarrier,
}


def available_carriers(config: Mapping[str, Any]) -> list[str]:
    """Keys of the couriers usable with the entry's ``config`` (data)."""
    return [key for key, carrier in CARRIERS.items() if carrier.available(config)]


def create_carriers(
    session: aiohttp.ClientSession, config: Mapping[str, Any]
) -> dict[str, Carrier]:
    """Build every available courier around a shared HTTP session."""
    return {
        key: carrier.create(session, config)
        for key, carrier in CARRIERS.items()
        if carrier.available(config)
    }
