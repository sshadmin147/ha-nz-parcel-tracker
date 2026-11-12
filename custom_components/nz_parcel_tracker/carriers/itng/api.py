"""Client for Freightways' "ITNG" public tracking pages.

Post Haste and NZ Couriers (both Freightways brands) publish the same
server-rendered tracking page, keyed on a customer number and a consignment ID.
Only the host differs, so the page client lives here and each courier supplies
its URL and its error class.

Keeps the contract the coordinator relies on:

* ``async_get_parcel`` returns a small dict (the page's events) on success,
* returns ``None`` when the page says it has no information for the
  consignment (a normal, expected state, never an error),
* raises the courier's error class for anything else, including a page whose
  layout we do not recognise, with ``status_code`` and ``retry_after`` set as for
  the other couriers,
* lets ``aiohttp.ClientError`` propagate untouched.
"""

from __future__ import annotations

from html import unescape
import re
from typing import Any, ClassVar

import aiohttp

from ..base import CarrierApiError

# One entry of the "Travel history": a title such as ``Pickup`` and the time in
# brackets, for example ``<h3 class="mk-transaction-title">Pickup<em> (11:34AM
# 24/8/2026) </em></h3>``.
_EVENT_RE = re.compile(
    r'<h3 class="mk-transaction-title">(?P<title>.*?)<em>\s*\((?P<time>[^)]*)\)\s*</em>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]*>")
_NO_INFORMATION = "no information available for the consignment"


def _text(value: str) -> str:
    return " ".join(unescape(_TAG_RE.sub(" ", value)).split())


def parse_events(page: str) -> list[dict[str, str]]:
    """Return ``{title, time}`` for every travel-history entry on the page.

    Only the title and time are read: the entry text names the courier and may
    include who signed for the parcel, which is deliberately never kept.
    """
    return [
        {"title": _text(match["title"]), "time": _text(match["time"])}
        for match in _EVENT_RE.finditer(page)
    ]


class ITNGApiClient:
    """Reads one courier's customer-label tracking page."""

    #: The courier's ``ITNG_TAndTServlet`` URL.
    url: ClassVar[str]
    #: The courier's error class (a :class:`CarrierApiError` subclass).
    error_class: ClassVar[type[CarrierApiError]]

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client with an aiohttp session."""
        self._session = session

    async def async_get_parcel(
        self, customer_number: str, consignment_id: str
    ) -> dict[str, Any] | None:
        """Fetch one consignment's events, or ``None`` if there is no information."""
        error = self.error_class
        async with self._session.get(
            self.url,
            params={
                "page": "1",
                "Key_Type": "CustomerLabel",
                "VCCA": "Enabled",
                "customer_number": customer_number,
                "consignment_id": consignment_id,
            },
        ) as response:
            if response.status == 429:
                retry_after_header = response.headers.get("Retry-After")
                try:
                    retry_after = (
                        float(retry_after_header) if retry_after_header else None
                    )
                except ValueError:
                    retry_after = None  # an HTTP-date, not seconds
                raise error("HTTP 429", status_code=429, retry_after=retry_after)
            if response.status != 200:
                raise error(f"HTTP {response.status}", status_code=response.status)
            page = await response.text()

        events = parse_events(page)
        if events:
            return {"events": events}
        if _NO_INFORMATION in page.lower():
            return None
        raise error("unrecognised page (layout may have changed)")
