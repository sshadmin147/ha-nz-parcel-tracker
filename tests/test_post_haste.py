"""Tests for the Post Haste courier: page client, mapping and code shape.

The page fixtures are synthetic but follow the layout of Post Haste's public
tracking page (``mk-transaction`` blocks); no real consignment is used.
"""

from __future__ import annotations

from datetime import UTC
import logging
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import aiohttp
import pytest

from custom_components.nz_parcel_tracker.carriers import CARRIERS, CarrierApiError
from custom_components.nz_parcel_tracker.carriers.post_haste import (
    PostHasteApiClient,
    PostHasteApiError,
    PostHasteCarrier,
)
from custom_components.nz_parcel_tracker.carriers.post_haste.api import parse_events
from custom_components.nz_parcel_tracker.carriers.post_haste.mapping import (
    map_event_status,
    map_parcel_status,
    normalize_parcel,
    split_code,
    to_iso,
    tracking_url,
)
from custom_components.nz_parcel_tracker.codes import valid_tracking_code
from custom_components.nz_parcel_tracker.const import ParcelStatus

CODE = "1234567 TESTX000001"
NZ = ZoneInfo("Pacific/Auckland")


def _block(title: str, when: str, text: str = "Scanned in area Somewhere") -> str:
    return (
        '<div class="transaction mk-transaction">'
        f'<h3 class="mk-transaction-title">{title}<em> ({when}) </em></h3>'
        f'<ul class="mk-transaction-text"><li>{text}</li></ul></div>'
    )


PICKUP = _block("Pickup", "11:34AM 24/8/2026")
ON_BOARD = _block("On Board", "10:49AM 25/8/2026")
DELIVERY = _block(
    "Delivery",
    "1:43PM 25/8/2026",
    'Delivered in area Somewhere<li>Signed by "A Person"</li>',
)


def _page(*blocks: str) -> str:
    return "<html><body><h2>Travel history</h2>" + "".join(blocks) + "</body></html>"


NO_INFORMATION = (
    "<html><body><p>There is no information available for the consignment "
    "specified. Please contact your local branch.</p></body></html>"
)


def _session_returning(status: int, body: str = "", headers=None) -> MagicMock:
    response = AsyncMock()
    response.status = status
    response.headers = headers or {}
    response.text = AsyncMock(return_value=body)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


# --------------------------------------------------------------------- client


def test_parse_events_reads_titles_and_times_but_not_the_text():
    events = parse_events(_page(PICKUP, DELIVERY))
    assert events == [
        {"title": "Pickup", "time": "11:34AM 24/8/2026"},
        {"title": "Delivery", "time": "1:43PM 25/8/2026"},
    ]
    assert "Signed" not in str(events)


async def test_client_sends_the_customer_label_lookup():
    session = _session_returning(200, _page(PICKUP, ON_BOARD))
    parcel = await PostHasteApiClient(session).async_get_parcel(
        "1234567", "TESTX000001"
    )

    assert [e["title"] for e in parcel["events"]] == ["Pickup", "On Board"]
    assert "tools.posthaste.co.nz" in session.get.call_args.args[0]
    assert session.get.call_args.kwargs["params"] == {
        "page": "1",
        "Key_Type": "CustomerLabel",
        "VCCA": "Enabled",
        "customer_number": "1234567",
        "consignment_id": "TESTX000001",
    }


async def test_client_returns_none_when_post_haste_has_no_information():
    client = PostHasteApiClient(_session_returning(200, NO_INFORMATION))
    assert await client.async_get_parcel("1234567", "TESTX000001") is None


async def test_client_raises_when_the_layout_is_not_recognised():
    client = PostHasteApiClient(_session_returning(200, "<html>new design</html>"))
    with pytest.raises(PostHasteApiError, match="unrecognised page"):
        await client.async_get_parcel("1234567", "TESTX000001")


async def test_client_raises_on_error_status():
    client = PostHasteApiClient(_session_returning(500))
    with pytest.raises(PostHasteApiError) as err:
        await client.async_get_parcel("1234567", "TESTX000001")
    assert err.value.status_code == 500
    assert isinstance(err.value, CarrierApiError)
    assert str(err.value) == "Post Haste API request failed: HTTP 500"


@pytest.mark.parametrize(
    ("header", "expected"), [("30", 30.0), ("Wed, 21 Oct 2026", None), (None, None)]
)
async def test_client_reads_retry_after_on_429(header, expected):
    headers = {"Retry-After": header} if header else {}
    client = PostHasteApiClient(_session_returning(429, "", headers))
    with pytest.raises(PostHasteApiError) as err:
        await client.async_get_parcel("1234567", "TESTX000001")
    assert err.value.status_code == 429
    assert err.value.retry_after == expected


async def test_client_propagates_network_errors():
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))
    with pytest.raises(aiohttp.ClientError):
        await PostHasteApiClient(session).async_get_parcel("1", "2")


# -------------------------------------------------------------------- mapping


@pytest.mark.parametrize(
    ("title", "status"),
    [
        ("Pickup", ParcelStatus.IN_TRANSIT),
        ("On Board", ParcelStatus.OUT_FOR_DELIVERY),
        ("Delivery", ParcelStatus.DELIVERED),
        (None, ParcelStatus.UNKNOWN),
    ],
)
def test_status_mapping(title, status):
    assert map_parcel_status(title) is status


def test_unmapped_title_warns_once(caplog):
    with caplog.at_level(logging.WARNING):
        assert map_parcel_status("Held At Depot") is ParcelStatus.UNKNOWN
        assert map_event_status("Held At Depot") is None
    assert caplog.text.count("Unrecognised Post Haste status") == 1
    assert map_event_status(None) is None


def test_times_are_read_as_new_zealand_local_time():
    assert to_iso("11:34AM 24/8/2026", NZ) == "2026-08-24T11:34:00+12:00"
    assert to_iso("1:43pm 25/8/2026", NZ) == "2026-08-25T13:43:00+12:00"
    assert to_iso("11:34AM 24/8/2026", None) == "2026-08-24T11:34:00+00:00"
    assert to_iso("not a time", NZ) is None
    assert to_iso(None, NZ) is None


def _raw(*pairs: tuple[str, str]) -> dict:
    return {
        "tracking_code": CODE,
        "events": [{"title": t, "time": w} for t, w in pairs],
    }


def test_normalize_delivered_parcel():
    parcel = normalize_parcel(
        _raw(
            ("Delivery", "1:43PM 25/8/2026"),
            ("Pickup", "11:34AM 24/8/2026"),
            ("On Board", "10:49AM 25/8/2026"),
        ),
        zone=NZ,
    )
    assert parcel["carrier"] == "Post Haste"
    assert parcel["barcode"] == CODE
    assert parcel["status"] is ParcelStatus.DELIVERED
    assert parcel["raw_status"] == "Delivery"
    assert parcel["delivered"] is True
    assert parcel["delivered_at"] == "2026-08-25T13:43:00+12:00"
    assert parcel["history"] is None
    assert parcel["planned_from"] is None
    assert parcel["url"] == (
        "https://tools.posthaste.co.nz/phl/servlet/ITNG_TAndTServlet?page=1"
        "&Key_Type=CustomerLabel&VCCA=Enabled&customer_number=1234567"
        "&consignment_id=TESTX000001"
    )
    assert [e["title"] for e in parcel["raw"]["events"]] == [
        "Delivery",
        "Pickup",
        "On Board",
    ]


def test_normalize_in_progress_parcel_is_not_delivered():
    parcel = normalize_parcel(
        _raw(("Pickup", "11:34AM 24/8/2026"), ("On Board", "10:49AM 25/8/2026")),
        zone=NZ,
    )
    assert parcel["status"] is ParcelStatus.OUT_FOR_DELIVERY
    assert parcel["delivered"] is False
    assert parcel["delivered_at"] is None


def test_history_is_sorted_and_opt_in():
    parcel = normalize_parcel(
        _raw(
            ("On Board", "10:49AM 25/8/2026"),
            ("Pickup", "11:34AM 24/8/2026"),
            ("Pickup", "garbage"),
        ),
        include_history=True,
        zone=NZ,
    )
    assert [e["raw_status"] for e in parcel["history"]] == ["Pickup", "On Board"]
    assert parcel["history"][0]["status"] is ParcelStatus.IN_TRANSIT


def test_normalize_without_events_is_unknown():
    parcel = normalize_parcel({"tracking_code": CODE, "events": []})
    assert parcel["status"] is ParcelStatus.UNKNOWN
    assert parcel["raw_status"] is None
    assert parcel["barcode"] == CODE


def test_normalize_survives_unparseable_times():
    parcel = normalize_parcel(_raw(("Pickup", "soon")), zone=UTC)
    assert parcel["status"] is ParcelStatus.IN_TRANSIT


def test_split_code_and_url():
    assert split_code("1234567 testx000001") == ("1234567", "TESTX000001")
    assert split_code("1234567-TESTX000001") == ("1234567", "TESTX000001")
    assert split_code("1234567") is None
    assert split_code("TESTX000001") is None
    assert tracking_url(None) is None
    assert tracking_url("nonsense") is None


# -------------------------------------------------------------------- carrier


def test_carrier_is_registered_and_redacts_the_identifiers():
    assert "post_haste" in CARRIERS
    assert {"customer_number", "consignment_id"} <= PostHasteCarrier.redact_keys


@pytest.mark.parametrize("code", [CODE, "1234567-TESTX000001", "2020119 DESX0026044"])
def test_valid_codes(code):
    assert valid_tracking_code(code, "post_haste")


@pytest.mark.parametrize("code", ["TESTX000001", "12 345", "1234567 TESTX0000010123"])
def test_invalid_codes(code):
    assert not valid_tracking_code(code, "post_haste")


async def test_async_get_parcel_splits_the_code_for_the_client():
    client = AsyncMock()
    client.async_get_parcel.return_value = {"events": []}
    carrier = PostHasteCarrier(client)

    assert await carrier.async_get_parcel(CODE) == {"events": []}
    client.async_get_parcel.assert_awaited_once_with("1234567", "TESTX000001")
    client.async_get_parcel.reset_mock()
    assert await carrier.async_get_parcel("garbage") is None
    client.async_get_parcel.assert_not_awaited()


def test_prepare_raw_keeps_only_titles_and_times():
    carrier = PostHasteCarrier(AsyncMock())
    prepared = carrier.prepare_raw(
        {"events": [{"title": "Pickup", "time": "x", "text": "Signed by A"}, "junk"]},
        CODE,
    )
    assert prepared == {
        "tracking_code": CODE,
        "events": [{"title": "Pickup", "time": "x"}],
    }
    assert carrier.placeholder_raw(CODE) == {"tracking_code": CODE, "events": []}


async def test_async_prepare_loads_the_nz_zone(hass):
    carrier = PostHasteCarrier(AsyncMock())
    await carrier.async_prepare(hass)
    parcel = carrier.normalize(_raw(("Pickup", "11:34AM 24/8/2026")))
    assert parcel["raw"]["events"][0]["time"] == "11:34AM 24/8/2026"
    parcel = carrier.normalize(_raw(("Delivery", "1:43PM 25/8/2026")))
    assert parcel["delivered_at"] == "2026-08-25T13:43:00+12:00"


def test_create_builds_a_session_backed_carrier():
    assert isinstance(PostHasteCarrier.create(MagicMock(), {}), PostHasteCarrier)
