"""Constants for the NZ Parcel Tracker integration."""

from enum import StrEnum

from homeassistant.const import Platform

DOMAIN = "nz_parcel_tracker"


class ParcelStatus(StrEnum):
    """Parcel status published on the ``status`` field of each normalised parcel.

    Automations match on these values (for example ``status: out_for_delivery``),
    so renaming one is a breaking change. Listed in roughly the order a parcel
    moves through.
    """

    REGISTERED = "registered"  # Sender announced the parcel; not handed over yet
    IN_TRANSIT = "in_transit"  # In the carrier's network
    OUT_FOR_DELIVERY = "out_for_delivery"  # On a delivery vehicle today
    AT_PICKUP_POINT = "at_pickup_point"  # Ready to collect at a pickup location
    DELIVERED = "delivered"  # Handed over
    RETURNING = "returning"  # Failed delivery, going back to sender
    PROBLEM = "problem"  # Carrier reports an exception/issue
    UNKNOWN = "unknown"  # Raw status we have not mapped yet


PLATFORMS = [Platform.BUTTON, Platform.CALENDAR, Platform.SENSOR]

# Tracked parcels live in the config entry options as a list of
# ``{tracking_code, carrier}`` dicts. Couriers are tracked by public code with
# no account or parcel feed, so the user enters the codes themselves. ``carrier``
# is the key of a courier in ``carriers.CARRIERS``; entries saved before it
# existed have none and mean ``DEFAULT_CARRIER``.
CONF_PARCELS = "parcels"
CONF_TRACKING_CODE = "tracking_code"
CONF_CARRIER = "carrier"
DEFAULT_CARRIER = "nz_post"

# Delivered-parcels retention: keep delivered parcels visible for the last N
# days, or keep only the N most recent.
CONF_DELIVERED_FILTER_TYPE = "delivered_filter_type"
CONF_DELIVERED_FILTER_AMOUNT = "delivered_filter_amount"
DEFAULT_DELIVERED_FILTER_TYPE = "days"
DEFAULT_DELIVERED_FILTER_AMOUNT = 7

# Dynamic, status-driven polling with no user-facing interval option; the
# algorithm is described in the README's "Dynamic polling" section.
#
# Quiet window: no polling between these local hours except the two anchors
# below, for overnight / end-of-day catch-up.
QUIET_WINDOW_START_HOUR = 0
QUIET_WINDOW_END_HOUR = 6

# Cadence while polling is active (minutes). Hot = at least one tracked,
# not-yet-delivered parcel is out_for_delivery within HOT_LOOKAHEAD_HOURS of
# its planned_from (or has no planned_from at all); mid = anything else still
# in flight (registered, in_transit, at_pickup_point, unknown, problem,
# returning).
HOT_INTERVAL_MINUTES = 15
MID_INTERVAL_MINUTES = 45
HOT_LOOKAHEAD_HOURS = 1

# Small, stable per-install offset added to every computed interval so
# different installs don't all hit an anchor or tier boundary at the same
# second. Deterministic (hash of the config entry id), not random.
STAGGER_MINUTES = 7

# Per-parcel status history is opt-in and off by default: it is a large
# attribute, even though the timeline arrives in the same response and costs no
# extra request.
CONF_INCLUDE_HISTORY = "include_history"
DEFAULT_INCLUDE_HISTORY = False

# Cap each parcel's history to the most recent N events so the attribute stays
# well under HA's ~16 KB state-attribute limit.
HISTORY_MAX_EVENTS = 20
