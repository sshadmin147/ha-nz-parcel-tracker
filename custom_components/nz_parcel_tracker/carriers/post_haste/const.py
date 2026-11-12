"""Post Haste endpoints.

Post Haste has no JSON tracking API for customer-printed labels; the public
tracking page is a server-rendered HTML page keyed on the customer number and
the consignment ID (both are printed on the label and sit in the tracking link
the sender emails). An unknown consignment still answers HTTP 200, with a page
that says "There is no information available for the consignment specified".
Only this label type is supported; Post Haste's prepaid-ticket and charge-label
lookups use different keys.
"""

TRACKING_URL = "https://tools.posthaste.co.nz/phl/servlet/ITNG_TAndTServlet"
# Event times on the page are New Zealand local time.
TIMEZONE = "Pacific/Auckland"
