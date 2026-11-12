"""Post Haste: customer-label tracking through its public tracking page.

The page, the code format and the status mapping are shared with NZ Couriers;
see :mod:`..itng`. Only customer labels are supported: Post Haste's prepaid
ticket (``product_code`` and ``serial_number``) and charge label lookups use
different keys.
"""

from __future__ import annotations

from ..base import CarrierApiError
from ..itng import ITNGApiClient, ITNGCarrier

__all__ = ["PostHasteApiClient", "PostHasteApiError", "PostHasteCarrier"]


class PostHasteApiError(CarrierApiError):
    """Raised when a Post Haste request returns an unexpected response."""

    carrier_name = "Post Haste"


class PostHasteApiClient(ITNGApiClient):
    """Reads Post Haste's customer-label tracking page."""

    url = "https://tools.posthaste.co.nz/phl/servlet/ITNG_TAndTServlet"
    error_class = PostHasteApiError


class PostHasteCarrier(ITNGCarrier):
    """Post Haste customer-label parcels."""

    key = "post_haste"
    name = "Post Haste"
    client_class = PostHasteApiClient
