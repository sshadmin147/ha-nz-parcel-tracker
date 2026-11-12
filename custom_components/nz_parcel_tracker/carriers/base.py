"""The interface every courier implements.

The core (coordinator, entities, services, config flow) knows nothing about any
specific courier. It talks to a :class:`Carrier` and handles
:class:`CarrierApiError`; everything courier specific (endpoint, payload shape,
status wording, tracking code format, redaction list) lives in the courier's own
package under ``carriers/``.

To add a courier:

1. Create ``carriers/<key>/`` with an API client, a status mapping and a
   :class:`Carrier` subclass.
2. Add the subclass to ``CARRIERS`` in ``carriers/__init__.py``.
3. Add the key to the ``carrier`` selector in ``services.yaml``.
4. Add tests for the mapping, the client and the code format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import aiohttp


class CarrierApiError(Exception):
    """A courier's tracking endpoint returned something unusable.

    ``status_code`` is set on a non-2xx response and ``retry_after`` (seconds)
    when the courier sent a parseable ``Retry-After`` on a 429; the
    coordinator's backoff reads both. Subclasses set ``carrier_name`` so the
    message names the courier.
    """

    carrier_name: ClassVar[str] = "Carrier"

    def __init__(
        self,
        detail: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        """Store the status code and the ``Retry-After`` header, if any."""
        super().__init__(f"{self.carrier_name} API request failed: {detail}")
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


class Carrier(ABC):
    """One courier: how to fetch a parcel and turn it into the shared shape."""

    #: Stable identifier stored with each tracked parcel, for example ``nz_post``.
    key: ClassVar[str]
    #: Human-readable name, published as ``carrier`` on every parcel.
    name: ClassVar[str]
    #: Courier-specific payload field names to redact from diagnostics.
    redact_keys: ClassVar[frozenset[str]] = frozenset()

    @classmethod
    @abstractmethod
    def create(cls, session: aiohttp.ClientSession) -> Carrier:
        """Build the courier around Home Assistant's shared HTTP session."""

    @abstractmethod
    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one parcel's raw payload.

        Return ``None`` when the courier does not know the code (or has not
        scanned the parcel yet): a normal, expected state, never an error.
        Raise :class:`CarrierApiError` for anything else. Let
        ``aiohttp.ClientError`` propagate; the coordinator handles it.
        """

    @classmethod
    @abstractmethod
    def matches_code(cls, code: str) -> bool:
        """Whether ``code`` (already stripped and upper-cased) has this courier's shape.

        A class method so codes can be checked without building the courier.
        """

    @abstractmethod
    def prepare_raw(self, raw: dict[str, Any], tracking_code: str) -> dict[str, Any]:
        """Return the part of a payload that is safe to keep between polls.

        Must make sure the result carries ``tracking_code`` even when the
        courier's response left it out.
        """

    @abstractmethod
    def placeholder_raw(self, tracking_code: str) -> dict[str, Any]:
        """Return a minimal payload for a parcel the courier does not know yet."""

    @abstractmethod
    def normalize(
        self, raw: dict[str, Any], *, include_history: bool = False
    ) -> dict[str, Any]:
        """Return the shared parcel dict for a payload from :meth:`prepare_raw`.

        Build it with :func:`..parcels.build_parcel` so every courier publishes
        exactly the same set of keys.
        """
