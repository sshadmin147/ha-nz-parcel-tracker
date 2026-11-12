"""Aramex New Zealand: a courier behind the shared :class:`Carrier` interface."""

from __future__ import annotations

from datetime import tzinfo
import re
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..base import Carrier
from .api import AramexApiClient, AramexApiError
from .const import TIMEZONE
from .mapping import CARRIER_NAME, normalize_parcel, sanitize_tracking_payload

__all__ = ["AramexApiClient", "AramexApiError", "AramexCarrier"]

# Aramex labels seen so far are ``MP`` plus ten digits (``MP0085494934``) or
# eleven digits; the shape check is deliberately loose.
_LABEL_RE = re.compile(r"[A-Z0-9]{8,30}")


class AramexCarrier(Carrier):
    """Aramex New Zealand parcels, via Aramex's public tracking endpoint."""

    key = "aramex"
    name = CARRIER_NAME
    # Payload fields that identify a parcel (the scan text is kept; see mapping).
    redact_keys = frozenset({"LabelNumber"})

    def __init__(self, client: AramexApiClient, zone: tzinfo | None = None) -> None:
        """Wrap an API client; ``zone`` reads the date-only ETA (else UTC)."""
        self._client = client
        self._zone = zone

    @classmethod
    def create(cls, session: aiohttp.ClientSession) -> AramexCarrier:
        """Build the carrier around Home Assistant's shared HTTP session."""
        return cls(AramexApiClient(session))

    async def async_prepare(self, hass: HomeAssistant) -> None:
        """Load the New Zealand time zone off the event loop's critical path."""
        self._zone = await dt_util.async_get_time_zone(TIMEZONE)

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one parcel from Aramex."""
        return await self._client.async_get_parcel(tracking_code)

    @classmethod
    def matches_code(cls, code: str) -> bool:
        """Whether ``code`` could be an Aramex label."""
        compact = code.replace(" ", "").replace("-", "")
        return _LABEL_RE.fullmatch(compact) is not None

    def prepare_raw(self, raw: dict[str, Any], tracking_code: str) -> dict[str, Any]:
        """Keep the safe payload fields, falling back to the code we asked for."""
        raw.setdefault("tracking_code", tracking_code)
        return sanitize_tracking_payload(raw)

    def placeholder_raw(self, tracking_code: str) -> dict[str, Any]:
        """A label Aramex has not scanned yet: just its code and no scans."""
        return {"tracking_code": tracking_code, "result": {"Scans": []}}

    def normalize(
        self, raw: dict[str, Any], *, include_history: bool = False
    ) -> dict[str, Any]:
        """Map an Aramex payload to the shared parcel shape."""
        return normalize_parcel(raw, include_history=include_history, zone=self._zone)
