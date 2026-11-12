"""Tracking code helpers shared by the config flow and the services.

Courier independent: the shape of a valid code comes from the registered
couriers (see :mod:`.carriers`), and a pasted web address is always refused.
"""

from __future__ import annotations

from .carriers import CARRIERS

# Anything that is not a plain reference: a pasted tracking link, or a path or
# address fragment. Checked first so the user gets a specific message.
_LINK_TOKENS = ("HTTP", "WWW", "/", ":", ".", "@")


def normalize_tracking_code(value: str) -> str:
    """Strip and upper-case a tracking code without imposing a format mask."""
    return str(value or "").strip().upper()


def looks_like_link(value: str) -> bool:
    """Whether ``value`` looks like a web address rather than a tracking code."""
    upper = str(value or "").upper()
    return any(token in upper for token in _LINK_TOKENS)


def valid_tracking_code(value: str, carrier: str) -> bool:
    """Whether ``value`` is a plausible tracking code for the courier ``carrier``.

    Only the shape is checked, and never a link. The courier is always chosen
    by the user, never guessed from the code. A code that passes can still be
    unknown to the courier; the courier decides that.
    """
    code = normalize_tracking_code(value)
    if looks_like_link(code):
        return False
    courier = CARRIERS.get(carrier)
    return courier is not None and courier.matches_code(code)
