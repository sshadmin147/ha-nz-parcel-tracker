"""Post Haste: a courier behind the shared :class:`Carrier` interface.

A Post Haste customer label is tracked by two values, the customer number and the
consignment ID. They are entered together as one tracking code, separated by a
space or hyphen, for example ``2020119 DESX0026044``.
"""

from __future__ import annotations

from datetime import tzinfo
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..base import Carrier
from .api import PostHasteApiClient, PostHasteApiError
from .const import TIMEZONE
from .mapping import CARRIER_NAME, normalize_parcel, sanitize_payload, split_code

__all__ = ["PostHasteApiClient", "PostHasteApiError", "PostHasteCarrier"]


class PostHasteCarrier(Carrier):
    """Post Haste customer-label parcels, via the public tracking page."""

    key = "post_haste"
    name = CARRIER_NAME
    redact_keys = frozenset({"customer_number", "consignment_id"})

    def __init__(self, client: PostHasteApiClient, zone: tzinfo | None = None) -> None:
        """Wrap an API client; ``zone`` reads the page's local times (else UTC)."""
        self._client = client
        self._zone = zone

    @classmethod
    def create(cls, session: aiohttp.ClientSession) -> PostHasteCarrier:
        """Build the carrier around Home Assistant's shared HTTP session."""
        return cls(PostHasteApiClient(session))

    async def async_prepare(self, hass: HomeAssistant) -> None:
        """Load the New Zealand time zone without blocking the event loop."""
        self._zone = await dt_util.async_get_time_zone(TIMEZONE)

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one consignment from Post Haste."""
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
        """A consignment Post Haste has no information on yet: just its code."""
        return {"tracking_code": tracking_code, "events": []}

    def normalize(
        self, raw: dict[str, Any], *, include_history: bool = False
    ) -> dict[str, Any]:
        """Map a Post Haste payload to the shared parcel shape."""
        return normalize_parcel(raw, include_history=include_history, zone=self._zone)
