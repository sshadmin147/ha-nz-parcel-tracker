"""Tests for the Freightways tracking-page couriers (Post Haste and NZ Couriers).

Both couriers publish the same page, so these tests run against each of them.
The page fixtures are synthetic but follow the layout of the real public page
(``mk-transaction`` blocks); no real consignment is used.
"""

from __future__ import annotations

from datetime import UTC
import logging
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import aiohttp
import pytest

from custom_components.nz_parcel_tracker.carriers import CARRIERS, CarrierApiError
from custom_components.nz_parcel_tracker.carriers.itng.api import parse_events
from custom_components.nz_parcel_tracker.carriers.itng.mapping import (
    map_event_status,
    map_parcel_status,
    normalize_parcel,
    split_code,
    to_iso,
    tracking_url,
)
from custom_components.nz_parcel_tracker.carriers.nz_couriers import (
    NZCouriersApiClient,
    NZCouriersApiError,
    NZCouriersCarrier,
)
from custom_components.nz_parcel_tracker.carriers.post_haste import (
    PostHasteApiClient,
    PostHasteApiError,
    PostHasteCarrier,
)
from custom_components.nz_parcel_tracker.codes import valid_tracking_code
from custom_components.nz_parcel_tracker.const import ParcelStatus

CODE = "1234567 TESTX000001"
NZ = ZoneInfo("Pacific/Auckland")

COURIERS = [
    pytest.param(
        PostHasteCarrier,
        PostHasteApiClient,
        PostHasteApiError,
        "post_haste",
        "Post Haste",
        "tools.posthaste.co.nz/phl/servlet",
        id="post_haste",
    ),
    pytest.param(
        NZCouriersCarrier,
        NZCouriersApiClient,
        NZCouriersApiError,
        "nz_couriers",
        "NZ Couriers",
        "tools.nzcouriers.co.nz/nzc/servlet",
        id="nz_couriers",
    ),
]


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
    'Delivered in area Somewhere<li>Delivered to "A Person"</li>',
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
    assert "Person" not in str(events)


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
async def test_client_sends_the_customer_label_lookup(
    carrier, client, error, key, name, host
):
    session = _session_returning(200, _page(PICKUP, ON_BOARD))
    parcel = await client(session).async_get_parcel("1234567", "TESTX000001")

    assert [e["title"] for e in parcel["events"]] == ["Pickup", "On Board"]
    assert host in session.get.call_args.args[0]
    assert session.get.call_args.kwargs["params"] == {
        "page": "1",
        "Key_Type": "CustomerLabel",
        "VCCA": "Enabled",
        "customer_number": "1234567",
        "consignment_id": "TESTX000001",
    }


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
async def test_client_returns_none_when_there_is_no_information(
    carrier, client, error, key, name, host
):
    session = _session_returning(200, NO_INFORMATION)
    assert await client(session).async_get_parcel("1234567", "TESTX000001") is None


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
async def test_client_raises_when_the_layout_is_not_recognised(
    carrier, client, error, key, name, host
):
    session = _session_returning(200, "<html>new design</html>")
    with pytest.raises(error, match="unrecognised page"):
        await client(session).async_get_parcel("1234567", "TESTX000001")


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
async def test_client_raises_on_error_status_naming_the_courier(
    carrier, client, error, key, name, host
):
    with pytest.raises(error) as err:
        await client(_session_returning(500)).async_get_parcel("1", "2")
    assert err.value.status_code == 500
    assert isinstance(err.value, CarrierApiError)
    assert str(err.value) == f"{name} API request failed: HTTP 500"


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
@pytest.mark.parametrize(
    ("header", "expected"), [("30", 30.0), ("Wed, 21 Oct 2026", None), (None, None)]
)
async def test_client_reads_retry_after_on_429(
    carrier, client, error, key, name, host, header, expected
):
    headers = {"Retry-After": header} if header else {}
    with pytest.raises(error) as err:
        await client(_session_returning(429, "", headers)).async_get_parcel("1", "2")
    assert err.value.status_code == 429
    assert err.value.retry_after == expected


async def test_client_propagates_network_errors():
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))
    with pytest.raises(aiohttp.ClientError):
        await NZCouriersApiClient(session).async_get_parcel("1", "2")


# -------------------------------------------------------------------- mapping


@pytest.mark.parametrize(
    ("title", "status"),
    [
        ("Pickup", ParcelStatus.IN_TRANSIT),
        ("On Board", ParcelStatus.OUT_FOR_DELIVERY),
        ("Delivery", ParcelStatus.DELIVERED),
        ("Status", ParcelStatus.UNKNOWN),
        (None, ParcelStatus.UNKNOWN),
    ],
)
def test_status_mapping(title, status):
    assert map_parcel_status("X", title) is status


def test_unmapped_title_warns_once_but_the_informational_status_does_not(caplog):
    with caplog.at_level(logging.WARNING):
        assert map_parcel_status("Courier X", "Held At Depot") is ParcelStatus.UNKNOWN
        assert map_event_status("Courier X", "Held At Depot") is None
        assert map_event_status("Courier X", "Status") is None
        assert map_parcel_status("Courier X", "Status") is ParcelStatus.UNKNOWN
    assert caplog.text.count("Unrecognised Courier X status") == 1
    assert "status=Status" not in caplog.text
    assert map_event_status("Courier X", None) is None


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


def _normalize(raw, **kwargs):
    return normalize_parcel(
        raw,
        carrier_name="NZ Couriers",
        base_url="https://tools.nzcouriers.co.nz/nzc/servlet/ITNG_TAndTServlet",
        **kwargs,
    )


def test_normalize_delivered_parcel():
    parcel = _normalize(
        _raw(
            ("Delivery", "1:43PM 25/8/2026"),
            ("Pickup", "11:34AM 24/8/2026"),
            ("On Board", "10:49AM 25/8/2026"),
        ),
        zone=NZ,
    )
    assert parcel["carrier"] == "NZ Couriers"
    assert parcel["barcode"] == CODE
    assert parcel["status"] is ParcelStatus.DELIVERED
    assert parcel["raw_status"] == "Delivery"
    assert parcel["delivered"] is True
    assert parcel["delivered_at"] == "2026-08-25T13:43:00+12:00"
    assert parcel["history"] is None
    assert parcel["planned_from"] is None
    assert parcel["url"] == (
        "https://tools.nzcouriers.co.nz/nzc/servlet/ITNG_TAndTServlet?page=1"
        "&Key_Type=CustomerLabel&VCCA=Enabled&customer_number=1234567"
        "&consignment_id=TESTX000001"
    )
    assert [e["title"] for e in parcel["raw"]["events"]] == [
        "Delivery",
        "Pickup",
        "On Board",
    ]


def test_normalize_in_progress_parcel_is_not_delivered():
    parcel = _normalize(
        _raw(("Pickup", "11:34AM 24/8/2026"), ("On Board", "10:49AM 25/8/2026")),
        zone=NZ,
    )
    assert parcel["status"] is ParcelStatus.OUT_FOR_DELIVERY
    assert parcel["delivered"] is False
    assert parcel["delivered_at"] is None


def test_a_redelivered_parcel_is_delivered_at_the_last_delivery():
    """Delivered, picked up again, then delivered once more."""
    parcel = _normalize(
        _raw(
            ("Pickup", "11:44AM 14/7/2026"),
            ("On Board", "7:40AM 15/7/2026"),
            ("Delivery", "12:42PM 15/7/2026"),
            ("Pickup", "2:24PM 20/7/2026"),
            ("Status", "11:20AM 21/7/2026"),
            ("On Board", "6:48AM 27/7/2026"),
            ("Delivery", "9:55AM 27/7/2026"),
        ),
        zone=NZ,
    )
    assert parcel["status"] is ParcelStatus.DELIVERED
    assert parcel["delivered_at"] == "2026-07-27T09:55:00+12:00"


def test_an_informational_status_entry_never_decides_the_status():
    parcel = _normalize(
        _raw(("Delivery", "12:42PM 15/7/2026"), ("Status", "11:20AM 21/7/2026")),
        zone=NZ,
    )
    assert parcel["status"] is ParcelStatus.DELIVERED
    assert parcel["raw_status"] == "Delivery"


def test_a_parcel_with_only_informational_entries_is_unknown():
    parcel = _normalize(_raw(("Status", "11:20AM 21/7/2026")), zone=NZ)
    assert parcel["status"] is ParcelStatus.UNKNOWN


def test_history_is_sorted_and_opt_in_and_keeps_informational_entries():
    parcel = _normalize(
        _raw(
            ("On Board", "10:49AM 25/8/2026"),
            ("Status", "9:00AM 25/8/2026"),
            ("Pickup", "11:34AM 24/8/2026"),
            ("Pickup", "garbage"),
        ),
        include_history=True,
        zone=NZ,
    )
    assert [e["raw_status"] for e in parcel["history"]] == [
        "Pickup",
        "Status",
        "On Board",
    ]
    assert parcel["history"][0]["status"] is ParcelStatus.IN_TRANSIT
    assert parcel["history"][1]["status"] is None


def test_normalize_without_events_is_unknown():
    parcel = _normalize({"tracking_code": CODE, "events": []})
    assert parcel["status"] is ParcelStatus.UNKNOWN
    assert parcel["raw_status"] is None
    assert parcel["barcode"] == CODE


def test_normalize_survives_unparseable_times():
    parcel = _normalize(_raw(("Pickup", "soon")), zone=UTC)
    assert parcel["status"] is ParcelStatus.IN_TRANSIT


def test_split_code_and_url():
    assert split_code("1234567 testx000001") == ("1234567", "TESTX000001")
    assert split_code("1234567-TESTX000001") == ("1234567", "TESTX000001")
    assert split_code("1234567") is None
    assert split_code("TESTX000001") is None
    assert tracking_url("https://x", None) is None
    assert tracking_url("https://x", "nonsense") is None


# -------------------------------------------------------------------- carrier


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
def test_carrier_is_registered_and_redacts_the_identifiers(
    carrier, client, error, key, name, host
):
    assert CARRIERS[key] is carrier
    assert carrier.name == name
    assert {"customer_number", "consignment_id"} <= carrier.redact_keys


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
@pytest.mark.parametrize(
    "code", [CODE, "1234567-TESTX000001", "2020119 DESX0026044", "3351469 AGAG064544"]
)
def test_valid_codes(carrier, client, error, key, name, host, code):
    assert valid_tracking_code(code, key)


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
@pytest.mark.parametrize("code", ["TESTX000001", "12 345", "1234567 TESTX0000010123"])
def test_invalid_codes(carrier, client, error, key, name, host, code):
    assert not valid_tracking_code(code, key)


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
async def test_async_get_parcel_splits_the_code_for_the_client(
    carrier, client, error, key, name, host
):
    mock_client = AsyncMock()
    mock_client.async_get_parcel.return_value = {"events": []}
    instance = carrier(mock_client)

    assert await instance.async_get_parcel(CODE) == {"events": []}
    mock_client.async_get_parcel.assert_awaited_once_with("1234567", "TESTX000001")
    mock_client.async_get_parcel.reset_mock()
    assert await instance.async_get_parcel("garbage") is None
    mock_client.async_get_parcel.assert_not_awaited()


def test_prepare_raw_keeps_only_titles_and_times():
    carrier = NZCouriersCarrier(AsyncMock())
    prepared = carrier.prepare_raw(
        {"events": [{"title": "Pickup", "time": "x", "text": "Signed by A"}, "junk"]},
        CODE,
    )
    assert prepared == {
        "tracking_code": CODE,
        "events": [{"title": "Pickup", "time": "x"}],
    }
    assert carrier.placeholder_raw(CODE) == {"tracking_code": CODE, "events": []}


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
async def test_async_prepare_loads_the_nz_zone_and_names_the_courier(
    hass, carrier, client, error, key, name, host
):
    instance = carrier(AsyncMock())
    await instance.async_prepare(hass)
    parcel = instance.normalize(_raw(("Delivery", "1:43PM 25/8/2026")))
    assert parcel["carrier"] == name
    assert parcel["delivered_at"] == "2026-08-25T13:43:00+12:00"
    assert host in parcel["url"]


@pytest.mark.parametrize(
    ("carrier", "client", "error", "key", "name", "host"), COURIERS
)
def test_create_builds_a_session_backed_carrier(
    carrier, client, error, key, name, host
):
    assert isinstance(carrier.create(MagicMock(), {}), carrier)
