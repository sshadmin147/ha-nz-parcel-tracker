"""DHL Unified Shipment Tracking API constants.

DHL's official, documented tracking API (developer.dhl.com, "Shipment Tracking -
Unified"). One ``GET`` per tracking number, authenticated with the user's own
``DHL-API-Key``. It covers DHL Express and DHL eCommerce shipments. The standard
key allows 250 calls a day and one call every 5 seconds.
"""

TRACKING_API_URL = "https://api-eu.dhl.com/track/shipments"
REQUEST_TIMEOUT_SECONDS = 30
# DHL allows at most one call per 5 s per key, across every parcel, so requests
# are made one at a time and spaced out, never fired together.
MIN_REQUEST_GAP_SECONDS = 5.0
# English always, so DHL's status texts stay stable.
LANGUAGE = "en"
# Spent once to prove a key: DHL answers 404 for it when the key is accepted.
VALIDATION_CODE = "0000000000"
# Shown on every entity, as DHL's API terms ask.
ATTRIBUTION = "DHL data delivered by Deutsche Post DHL Group"
# Config entry data key for the user's API key.
CONF_API_KEY = "dhl_api_key"
