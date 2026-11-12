"""Aramex New Zealand endpoints.

The public tracking site is keyless: one GET per label returns JSON as
``{"generated_in": ..., "result": {...}}``. A label with no scans yet, or one
Aramex does not recognise, still answers HTTP 200 with a body that has no
``Scans`` list. Only the New Zealand site is used; Aramex Australia has its own
host and is out of scope.
"""

TRACKING_API_URL = "https://www.aramex.co.nz/umbraco/api/TrackingApi/GetTrackingData"
# Human-facing tracking page; ``?l=<label>`` deep-links a parcel.
TRACKING_URL_BASE = "https://www.aramex.co.nz/tools/track"
# ``DeliveryETADate`` is a date only, read in this zone.
TIMEZONE = "Pacific/Auckland"
