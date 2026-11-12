"""NZ Couriers: customer-label tracking through its public tracking page.

NZ Couriers and Post Haste are both Freightways brands and publish the same
page, so the page, the code format and the status mapping are shared; see
:mod:`..itng`. Only customer labels are supported. NZ Couriers' own website
also calls a JSON endpoint, but it returned nothing for the parcel it was tried
with, so the page is used.
"""

from __future__ import annotations

from ..base import CarrierApiError
from ..itng import ITNGApiClient, ITNGCarrier

__all__ = ["NZCouriersApiClient", "NZCouriersApiError", "NZCouriersCarrier"]


class NZCouriersApiError(CarrierApiError):
    """Raised when an NZ Couriers request returns an unexpected response."""

    carrier_name = "NZ Couriers"


class NZCouriersApiClient(ITNGApiClient):
    """Reads NZ Couriers' customer-label tracking page."""

    url = "https://tools.nzcouriers.co.nz/nzc/servlet/ITNG_TAndTServlet"
    error_class = NZCouriersApiError


class NZCouriersCarrier(ITNGCarrier):
    """NZ Couriers customer-label parcels."""

    key = "nz_couriers"
    name = "NZ Couriers"
    client_class = NZCouriersApiClient
