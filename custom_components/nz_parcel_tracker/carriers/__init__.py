"""Registry of the couriers this integration can track.

Adding a courier means adding its class to :data:`CARRIERS`; see
:mod:`.base` for the interface and the steps.
"""

from __future__ import annotations

import aiohttp

from .aramex import AramexCarrier
from .base import Carrier, CarrierApiError
from .nz_post import NZPostCarrier

__all__ = [
    "CARRIERS",
    "Carrier",
    "CarrierApiError",
    "create_carriers",
]

#: Every supported courier by key. The user always picks the courier for a
#: parcel (codes are never guessed), so the order only affects the selector.
CARRIERS: dict[str, type[Carrier]] = {
    AramexCarrier.key: AramexCarrier,
    NZPostCarrier.key: NZPostCarrier,
}


def create_carriers(session: aiohttp.ClientSession) -> dict[str, Carrier]:
    """Build one instance of every courier around a shared HTTP session."""
    return {key: carrier.create(session) for key, carrier in CARRIERS.items()}
