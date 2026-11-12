"""NZ Post: the first courier behind the shared :class:`Carrier` interface."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import aiohttp

from ..base import Carrier
from .api import NZPostApiClient, NZPostApiError
from .mapping import CARRIER_NAME, normalize_parcel, sanitize_raw_parcel

__all__ = ["NZPostApiClient", "NZPostApiError", "NZPostCarrier"]

# NZ Post references are numeric, UPU (for example ``RA123456789NZ``) or other
# alphanumeric codes of 8 to 30 characters. Spaces and hyphens are tolerated
# because people paste codes in groups, but they are ignored when checking.
_TRACKING_CODE_RE = re.compile(r"[A-Z0-9]{8,30}")


class NZPostCarrier(Carrier):
    """NZ Post parcels, tracked through NZ Post's public tracking endpoint."""

    key = "nz_post"
    name = CARRIER_NAME
    # Payload fields that identify a person, an address or a parcel.
    redact_keys = frozenset(
        {
            "tracking_reference",
            "trackingNumber",
            "signed_by",
            "depot_name",
            "run_name",
            "pbu",
            "seqref",
        }
    )

    def __init__(self, client: NZPostApiClient) -> None:
        """Wrap an API client (a mock in tests, a session-backed one in HA)."""
        self._client = client

    @classmethod
    def create(
        cls, session: aiohttp.ClientSession, config: Mapping[str, Any]
    ) -> NZPostCarrier:
        """Build the carrier around Home Assistant's shared HTTP session."""
        return cls(NZPostApiClient(session))

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        """Fetch one parcel from NZ Post."""
        return await self._client.async_get_parcel(tracking_code)

    @classmethod
    def matches_code(cls, code: str) -> bool:
        """Whether ``code`` has the shape of a NZ Post reference."""
        compact = code.replace(" ", "").replace("-", "")
        return _TRACKING_CODE_RE.fullmatch(compact) is not None

    def prepare_raw(self, raw: dict[str, Any], tracking_code: str) -> dict[str, Any]:
        """Keep the safe payload fields, falling back to the code we asked for."""
        raw.setdefault("tracking_reference", tracking_code)
        return sanitize_raw_parcel(raw)

    def placeholder_raw(self, tracking_code: str) -> dict[str, Any]:
        """A parcel NZ Post has not scanned yet: just its code."""
        return {"tracking_reference": tracking_code}

    def normalize(
        self, raw: dict[str, Any], *, include_history: bool = False
    ) -> dict[str, Any]:
        """Map a NZ Post payload to the shared parcel shape."""
        return normalize_parcel(raw, include_history=include_history)
