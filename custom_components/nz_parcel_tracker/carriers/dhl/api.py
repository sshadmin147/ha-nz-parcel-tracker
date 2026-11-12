"""DHL Unified Shipment Tracking API client.

Keeps the contract the coordinator relies on:

* ``async_get_parcel`` returns the first shipment dict DHL knows for the number,
* returns ``None`` on a 404 (DHL has no such shipment: normal, never an error),
* raises :class:`DHLApiError` for anything else, with ``status_code`` set on a
  non-2xx response and ``retry_after`` (seconds) set on a 429,
* lets ``aiohttp.ClientError`` propagate untouched.

Calls are spaced at least ``min_gap`` seconds apart, whatever number of parcels
ask at once, because DHL rate-limits one call per 5 s per key. The key is never
logged and the request URL (which carries the tracking number) is not logged.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import logging
import time
from typing import Any

import aiohttp

from ..base import CarrierApiError
from .const import (
    LANGUAGE,
    MIN_REQUEST_GAP_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    TRACKING_API_URL,
    VALIDATION_CODE,
)

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)


class DHLApiError(CarrierApiError):
    """Raised when a DHL API call returns an unexpected response."""

    carrier_name = "DHL"


def _retry_after(value: str | None) -> float | None:
    """Parse ``Retry-After`` as delta-seconds or an HTTP date."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - datetime.now(UTC)).total_seconds())


class DHLApiClient:
    """Fetches one tracking number at a time with the user's API key."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        min_gap: float = MIN_REQUEST_GAP_SECONDS,
    ) -> None:
        """Hold the shared session and the key; ``min_gap`` spaces the calls."""
        self._session = session
        self._api_key = api_key
        self._min_gap = min_gap
        self._lock = asyncio.Lock()
        self._last_call: float | None = None

    async def _get(self, code: str) -> tuple[int, Any, str | None]:
        """Make one spaced request; return ``(status, body, retry_after_header)``."""
        async with self._lock:
            if self._last_call is not None:
                wait = self._min_gap - (time.monotonic() - self._last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
            try:
                async with self._session.get(
                    TRACKING_API_URL,
                    params={"trackingNumber": code, "language": LANGUAGE},
                    headers={
                        "DHL-API-Key": self._api_key,
                        "accept": "application/json",
                    },
                    timeout=_TIMEOUT,
                ) as response:
                    status = response.status
                    retry_after = response.headers.get("Retry-After")
                    body = None
                    if status == 200:
                        try:
                            body = await response.json(content_type=None)
                        except ValueError as err:
                            raise DHLApiError("unparseable body") from err
            finally:
                self._last_call = time.monotonic()
        _LOGGER.debug("DHL API: GET /track/shipments -> HTTP %s", status)
        return status, body, retry_after

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Return DHL's shipment for ``tracking_code``, or ``None`` if unknown."""
        status, body, retry_after = await self._get(tracking_code)
        if status == 404:
            return None
        if status == 429:
            raise DHLApiError(
                "HTTP 429", status_code=429, retry_after=_retry_after(retry_after)
            )
        if status in (401, 403):
            raise DHLApiError(
                f"HTTP {status} (DHL rejected the API key)", status_code=status
            )
        if status != 200:
            raise DHLApiError(f"HTTP {status}", status_code=status)
        if not isinstance(body, dict):
            raise DHLApiError("unexpected body (not a JSON object)")
        shipments = [s for s in body.get("shipments") or [] if isinstance(s, dict)]
        if not shipments:
            return None
        for shipment in shipments:
            if str(shipment.get("id", "")).upper() == tracking_code.upper():
                return shipment
        return shipments[0]

    async def async_check_key(self) -> str | None:
        """Prove the key with one call: ``None`` if accepted, else an error name."""
        try:
            status, _, _ = await self._get(VALIDATION_CODE)
        except (aiohttp.ClientError, TimeoutError, DHLApiError):
            return "cannot_connect"
        if status in (401, 403):
            return "invalid_api_key"
        if status in (200, 404):
            return None
        return "cannot_connect"
