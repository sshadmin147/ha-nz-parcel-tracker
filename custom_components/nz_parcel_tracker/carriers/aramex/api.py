"""Aramex New Zealand public tracking API client.

Keeps the contract the coordinator relies on:

* ``async_get_parcel`` returns the raw per-parcel dict on success,
* returns ``None`` when Aramex says the label is unknown or not yet scanned (a
  normal, expected state, never an error),
* raises :class:`AramexApiError` for anything else, with ``status_code`` set on
  a non-2xx response and ``retry_after`` set when a 429 carried a
  ``Retry-After`` in seconds,
* lets ``aiohttp.ClientError`` propagate untouched.
"""

from __future__ import annotations

from typing import Any

import aiohttp

from ..base import CarrierApiError
from .const import TRACKING_API_URL


class AramexApiError(CarrierApiError):
    """Raised when an Aramex API call returns an unexpected response."""

    carrier_name = "Aramex"


class AramexApiClient:
    """Client for the public Aramex New Zealand tracking endpoint."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client with an aiohttp session."""
        self._session = session

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one parcel's tracking details, or ``None`` if unknown."""
        async with self._session.get(
            TRACKING_API_URL,
            params={"LabelNo": tracking_code, "dataFormat": "json"},
        ) as response:
            if response.status == 429:
                retry_after_header = response.headers.get("Retry-After")
                try:
                    retry_after = (
                        float(retry_after_header) if retry_after_header else None
                    )
                except ValueError:
                    retry_after = None  # an HTTP-date, not seconds
                raise AramexApiError(
                    "HTTP 429", status_code=429, retry_after=retry_after
                )
            if response.status != 200:
                raise AramexApiError(
                    f"HTTP {response.status}", status_code=response.status
                )
            try:
                # content_type=None: consumer endpoints routinely serve JSON as
                # text/plain, and aiohttp would otherwise refuse to parse it.
                payload = await response.json(content_type=None)
            except ValueError as err:
                raise AramexApiError(f"unparseable body ({err})") from err

        if not isinstance(payload, dict):
            raise AramexApiError("unexpected body (not a JSON object)")

        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("Scans"), list):
            return None
        return {"result": result, "tracking_code": tracking_code}
