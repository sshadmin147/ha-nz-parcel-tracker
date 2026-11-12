"""Shared carrier for Freightways' "ITNG" customer-label tracking pages.

Only customer labels are supported (not prepaid tickets, charge labels or
barcodes).

Post Haste and NZ Couriers publish the same page. A customer label is tracked
by two values, the customer number and the consignment ID, entered together as
one tracking code separated by a space or hyphen, for example
``2020119 DESX0026044``. A courier subclasses :class:`ITNGCarrier` and names its
key, its display name and its two client classes.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import tzinfo
from typing import Any, ClassVar

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..base import Carrier
from .api import ITNGApiClient
from .mapping import normalize_parcel, sanitize_payload, split_code

__all__ = ["ITNGApiClient", "ITNGCarrier"]

# Event times on the page are New Zealand local time.
TIMEZONE = "Pacific/Auckland"


class ITNGCarrier(Carrier):
    """A Freightways brand whose customer labels are tracked through its page."""

    redact_keys = frozenset({"customer_number", "consignment_id"})
    #: The courier's page client class.
    client_class: ClassVar[type[ITNGApiClient]]

    def __init__(self, client: ITNGApiClient, zone: tzinfo | None = None) -> None:
        """Wrap an API client; ``zone`` reads the page's local times (else UTC)."""
        self._client = client
        self._zone = zone

    @classmethod
    def create(
        cls, session: aiohttp.ClientSession, config: Mapping[str, Any]
    ) -> ITNGCarrier:
        """Build the carrier around Home Assistant's shared HTTP session."""
        return cls(cls.client_class(session))

    async def async_prepare(self, hass: HomeAssistant) -> None:
        """Load the New Zealand time zone without blocking the event loop."""
        self._zone = await dt_util.async_get_time_zone(TIMEZONE)

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one consignment from the courier."""
        parts = split_code(tracking_code)
        if parts is None:
            return None
        return await self._client.async_get_parcel(*parts)

    @classmethod
    def matches_code(cls, code: str) -> bool:
        """Whether ``code`` is ``<customer number> <consignment id>``."""
        return split_code(code) is not None

    def prepare_raw(self, raw: dict[str, Any], tracking_code: str) -> dict[str, Any]:
        """Keep each event's title and time, and the code we asked for."""
        raw.setdefault("tracking_code", tracking_code)
        return sanitize_payload(raw)

    def placeholder_raw(self, tracking_code: str) -> dict[str, Any]:
        """A consignment with no information yet: just its code."""
        return {"tracking_code": tracking_code, "events": []}

    def normalize(
        self, raw: dict[str, Any], *, include_history: bool = False
    ) -> dict[str, Any]:
        """Map a payload to the shared parcel shape."""
        return normalize_parcel(
            raw,
            carrier_name=self.name,
            base_url=self.client_class.url,
            include_history=include_history,
            zone=self._zone,
        )
