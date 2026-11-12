"""NZ Post specific constants."""

# ``TRACKING_API_URL`` is the consumer tracking endpoint the integration polls;
# ``TRACKING_URL_BASE`` is the human-facing deep link surfaced on each parcel's
# ``url`` field. The endpoint is public and keyless, is keyed on the
# ``tracking_reference`` query parameter, may serve JSON as text/plain, and
# answers a code it does not know (or has not scanned yet) with a ``results``
# list that is empty or carries ``errors`` (or ``status_code`` 2).
TRACKING_API_URL = "https://tools.nzpost.co.nz/tracking/api/parceltrack/parcels"
# Confirmed deep-link format: https://www.nzpost.co.nz/tools/tracking?trackid=<code>
TRACKING_URL_BASE = "https://www.nzpost.co.nz/tools/tracking"
