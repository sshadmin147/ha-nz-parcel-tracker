"""Registry of the couriers this integration can track.

Adding a courier means adding its class to :data:`CARRIERS`; see
:mod:`.base` for the interface and the steps.
"""

from __future__ import annotations

import aiohttp

from .base import Carrier, CarrierApiError
from .nz_post import NZPostCarrier

__all__ = [
    "CARRIERS",
    "Carrier",
    "CarrierApiError",
    "create_carriers",
    "detect_carrier",
]

#: Every supported courier by key. Order matters: when a tracking code fits
#: more than one courier, :func:`detect_carrier` picks the first.
CARRIERS: dict[str, type[Carrier]] = {NZPostCarrier.key: NZPostCarrier}


def create_carriers(session: aiohttp.ClientSession) -> dict[str, Carrier]:
    """Build one instance of every courier around a shared HTTP session."""
    return {key: carrier.create(session) for key, carrier in CARRIERS.items()}


def detect_carrier(code: str) -> str | None:
    """Return the key of the first courier whose code shape matches ``code``."""
    for key, carrier in CARRIERS.items():
        if carrier.matches_code(code):
            return key
    return None
