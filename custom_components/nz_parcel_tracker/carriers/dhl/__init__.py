"""DHL: a courier behind the shared :class:`Carrier` interface.

Uses DHL's official Unified Shipment Tracking API with the user's own API key
(see ``docs/dhl-api-key.md``). Without a key the courier is not available.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import aiohttp

from ..base import Carrier
from .api import DHLApiClient, DHLApiError
from .const import ATTRIBUTION, CONF_API_KEY
from .mapping import CARRIER_NAME, normalize_parcel, sanitize_shipment

__all__ = ["DHLApiClient", "DHLApiError", "DHLCarrier"]

# DHL tracking numbers vary a lot (10 digit Express waybills, ``JJD...``,
# ``GM...``, ``3S...`` and others), so only a broad shape is checked.
_TRACKING_CODE_RE = re.compile(r"[A-Z0-9]{8,30}")


class DHLCarrier(Carrier):
    """DHL parcels, tracked through DHL's official API."""

    key = "dhl"
    name = CARRIER_NAME
    config_key = CONF_API_KEY
    attribution = ATTRIBUTION
    # The key is a secret; the payload carries the tracking number and service.
    redact_keys = frozenset({CONF_API_KEY, "id"})

    def __init__(self, client: DHLApiClient) -> None:
        """Wrap an API client (a mock in tests, a session-backed one in HA)."""
        self._client = client

    @classmethod
    def create(
        cls, session: aiohttp.ClientSession, config: Mapping[str, Any]
    ) -> DHLCarrier:
        """Build the carrier with the user's API key from the entry data."""
        return cls(DHLApiClient(session, config[CONF_API_KEY]))

    @classmethod
    async def async_validate_config(
        cls, session: aiohttp.ClientSession, value: str
    ) -> str | None:
        """Prove the API key with one call to DHL."""
        return await DHLApiClient(session, value, min_gap=0).async_check_key()

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one shipment from DHL."""
        return await self._client.async_get_parcel(tracking_code)

    @classmethod
    def matches_code(cls, code: str) -> bool:
        """Whether ``code`` has a plausible DHL tracking number shape."""
        compact = code.replace(" ", "").replace("-", "")
        return _TRACKING_CODE_RE.fullmatch(compact) is not None

    def prepare_raw(self, raw: dict[str, Any], tracking_code: str) -> dict[str, Any]:
        """Keep the safe shipment fields, tagged with the number we asked for."""
        raw["tracking_code"] = tracking_code
        return sanitize_shipment(raw)

    def placeholder_raw(self, tracking_code: str) -> dict[str, Any]:
        """A number DHL does not know yet: just the code."""
        return {"tracking_code": tracking_code}

    def normalize(
        self, raw: dict[str, Any], *, include_history: bool = False
    ) -> dict[str, Any]:
        """Map a DHL shipment to the shared parcel shape."""
        return normalize_parcel(raw, include_history=include_history)
