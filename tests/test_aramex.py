"""Tests for the Aramex courier: client, mapping, code shape and ETA window."""

from __future__ import annotations

from datetime import UTC
import json
import logging
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import aiohttp
import pytest

from custom_components.nz_parcel_tracker.carriers import CARRIERS, CarrierApiError
from custom_components.nz_parcel_tracker.carriers.aramex import (
    AramexApiClient,
    AramexApiError,
    AramexCarrier,
)
from custom_components.nz_parcel_tracker.carriers.aramex.mapping import (
    eta_window,
    map_event_status,
    map_parcel_status,
    normalize_parcel,
    sanitize_status_text,
    tracking_url,
)
from custom_components.nz_parcel_tracker.codes import valid_tracking_code
from custom_components.nz_parcel_tracker.const import ParcelStatus
from custom_components.nz_parcel_tracker.parcels import build_parcel

CODE = "MP0085494934"
NZ = ZoneInfo("Pacific/Auckland")


def _scan(code: str, when: str, text: str) -> dict:
    return {"Status": code, "RealDateTime": when, "StatusDescription": text}


def _payload(scans: list[dict], eta: str | None = None) -> dict:
    result = {"LabelNumber": CODE, "Scans": scans}
    if eta:
        result["DeliveryETADate"] = eta
    return {"tracking_code": CODE, "result": result}


ACTIVE = [
    _scan("PP8", "2026-04-27T23:03:58Z", "Shipment announced"),
    _scan("PPP", "2026-04-28T15:52:17Z", "At sorting facility"),
    _scan("ONB", "2026-04-29T08:46:00Z", "Out for delivery"),
]
DELIVERED = [*ACTIVE, _scan("R36", "2026-04-29T13:12:42Z", "Delivered")]


def _session_returning(status: int, body: object = None, headers=None) -> MagicMock:
    response = AsyncMock()
    response.status = status
    response.headers = headers or {}
    if isinstance(body, str):
        response.json = AsyncMock(side_effect=json.JSONDecodeError("x", body, 0))
    else:
        response.json = AsyncMock(return_value=body)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session


# --------------------------------------------------------------------- client


async def test_client_returns_parcel_and_uses_the_nz_host():
    session = _session_returning(
        200, {"generated_in": 1, "result": {"LabelNumber": CODE, "Scans": []}}
    )
    parcel = await AramexApiClient(session).async_get_parcel(CODE)

    assert parcel["tracking_code"] == CODE
    assert "aramex.co.nz" in session.get.call_args.args[0]
    assert session.get.call_args.kwargs["params"] == {
        "LabelNo": CODE,
        "dataFormat": "json",
    }


@pytest.mark.parametrize(
    "body",
    [{"error": "Label does not have any scans."}, {"result": {"LabelNumber": CODE}}],
)
async def test_client_returns_none_for_unknown_or_unscanned(body):
    assert (
        await AramexApiClient(_session_returning(200, body)).async_get_parcel(CODE)
        is None
    )


async def test_client_raises_on_error_status_with_the_code():
    with pytest.raises(AramexApiError) as err:
        await AramexApiClient(_session_returning(500, {})).async_get_parcel(CODE)
    assert err.value.status_code == 500
    assert isinstance(err.value, CarrierApiError)
    assert str(err.value) == "Aramex API request failed: HTTP 500"


@pytest.mark.parametrize(
    ("header", "expected"), [("30", 30.0), ("Wed, 21 Oct 2026", None), (None, None)]
)
async def test_client_reads_retry_after_on_429(header, expected):
    headers = {"Retry-After": header} if header else {}
    client = AramexApiClient(_session_returning(429, {}, headers))
    with pytest.raises(AramexApiError) as err:
        await client.async_get_parcel(CODE)
    assert err.value.status_code == 429
    assert err.value.retry_after == expected


@pytest.mark.parametrize("body", ["not json", ["not", "a", "dict"]])
async def test_client_raises_on_bad_body(body):
    with pytest.raises(AramexApiError):
        await AramexApiClient(_session_returning(200, body)).async_get_parcel(CODE)


async def test_client_propagates_network_errors():
    session = MagicMock()
    session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))
    with pytest.raises(aiohttp.ClientError):
        await AramexApiClient(session).async_get_parcel(CODE)


# -------------------------------------------------------------------- mapping


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("PP8", ParcelStatus.REGISTERED),
        ("PPP", ParcelStatus.IN_TRANSIT),
        ("ONB", ParcelStatus.OUT_FOR_DELIVERY),
        ("R36", ParcelStatus.DELIVERED),
        ("U03", ParcelStatus.PROBLEM),
        ("RTS", ParcelStatus.RETURNING),
        (None, ParcelStatus.UNKNOWN),
    ],
)
def test_status_mapping(code, status):
    assert map_parcel_status(code) is status


def test_unmapped_status_warns_once_and_history_keeps_none(caplog):
    with caplog.at_level(logging.WARNING):
        assert map_parcel_status("ZZZ-NEW") is ParcelStatus.UNKNOWN
        assert map_event_status("ZZZ-NEW") is None
    assert caplog.text.count("Unrecognised Aramex status") == 1
    assert map_event_status(None) is None


def test_sanitize_status_text():
    assert sanitize_status_text(" At\x00 depot \n now ") == "At depot now"
    assert sanitize_status_text(5) is None
    assert sanitize_status_text("   ") is None


def test_normalize_active_parcel_has_the_shared_shape():
    parcel = normalize_parcel(_payload(ACTIVE), zone=NZ)

    assert list(parcel) == list(
        build_parcel(
            carrier="x",
            barcode=None,
            status=ParcelStatus.UNKNOWN,
            raw_status=None,
            delivered=False,
        )
    )
    assert parcel["carrier"] == "Aramex"
    assert parcel["status"] is ParcelStatus.OUT_FOR_DELIVERY
    assert parcel["raw_status"] == "Out for delivery"
    assert parcel["delivered"] is False
    assert parcel["history"] is None
    assert parcel["url"] == f"https://www.aramex.co.nz/tools/track?l={CODE}"
    assert parcel["raw"] == {
        "status": "ONB",
        "status_text": "Out for delivery",
        "timestamp": "2026-04-29T08:46:00Z",
    }


def test_normalize_delivered_clears_the_eta_window():
    parcel = normalize_parcel(_payload(DELIVERED, "30/04/2026"), zone=NZ)
    assert parcel["delivered"] is True
    assert parcel["delivered_at"] == "2026-04-29T13:12:42Z"
    assert parcel["planned_from"] is None
    assert parcel["planned_to"] is None


def test_eta_becomes_an_all_day_window_in_new_zealand():
    parcel = normalize_parcel(_payload(ACTIVE, "30/04/2026"), zone=NZ)
    assert parcel["planned_from"] == "2026-04-30T00:00:00+12:00"
    assert parcel["planned_to"].startswith("2026-04-30T23:59:59")
    assert parcel["planned_to"].endswith("+12:00")


def test_eta_window_falls_back_to_utc_and_ignores_bad_dates():
    assert eta_window("30/04/2026", None)[0] == "2026-04-30T00:00:00+00:00"
    assert eta_window("30/04/2026", UTC)[0] == "2026-04-30T00:00:00+00:00"
    assert eta_window("garbage", NZ) == (None, None)
    assert eta_window(None, NZ) == (None, None)
    assert eta_window("", NZ) == (None, None)


def test_history_is_sorted_capped_and_opt_in():
    scans = [
        _scan("ONB", "2026-04-29T08:46:00Z", "Out for delivery"),
        _scan("PP8", "2026-04-27T23:03:58Z", "Shipment announced"),
        {"Status": "PPP", "Date": "2026-04-28T15:52:17Z"},
        {"Status": "PPP"},
        "junk",
    ]
    parcel = normalize_parcel(_payload(scans), include_history=True, zone=NZ)
    assert [e["status"] for e in parcel["history"]] == [
        ParcelStatus.REGISTERED,
        ParcelStatus.IN_TRANSIT,
        ParcelStatus.OUT_FOR_DELIVERY,
    ]
    assert parcel["history"][1]["raw_status"] == "PPP"  # no text: the code


def test_normalize_with_no_scans_is_unknown():
    parcel = normalize_parcel({"tracking_code": CODE, "result": {"Scans": []}})
    assert parcel["status"] is ParcelStatus.UNKNOWN
    assert parcel["barcode"] == CODE
    assert parcel["raw"]["timestamp"] is None


def test_normalize_survives_a_malformed_payload():
    parcel = normalize_parcel({"tracking_code": CODE, "result": "nope"})
    assert parcel["barcode"] == CODE


def test_tracking_url_needs_a_code():
    assert tracking_url(None) is None


# -------------------------------------------------------------------- carrier


def test_carrier_is_registered_and_redacts_the_label():
    assert "aramex" in CARRIERS
    assert "LabelNumber" in AramexCarrier.redact_keys


def test_prepare_raw_drops_everything_but_the_safe_fields():
    carrier = AramexCarrier(AsyncMock())
    raw = {"result": {"Scans": [{"Status": "ONB", "Consignee": "A Person"}]}}
    prepared = carrier.prepare_raw(raw, CODE)
    assert prepared["tracking_code"] == CODE
    assert "Consignee" not in json.dumps(prepared)
    assert carrier.placeholder_raw(CODE)["result"]["Scans"] == []


async def test_async_get_parcel_delegates_to_the_client():
    client = AsyncMock()
    client.async_get_parcel.return_value = _payload(ACTIVE)
    assert await AramexCarrier(client).async_get_parcel(CODE) == _payload(ACTIVE)
    client.async_get_parcel.assert_awaited_once_with(CODE)


async def test_async_prepare_loads_the_nz_zone(hass):
    carrier = AramexCarrier(AsyncMock())
    await carrier.async_prepare(hass)
    parcel = carrier.normalize(_payload(ACTIVE, "30/04/2026"))
    assert parcel["planned_from"] == "2026-04-30T00:00:00+12:00"


def test_create_builds_a_session_backed_carrier():
    assert isinstance(AramexCarrier.create(MagicMock()), AramexCarrier)


@pytest.mark.parametrize("code", ["MP0085494934", "MP 0085-494934", "39134643030"])
def test_aramex_accepts_its_label_shapes(code):
    assert valid_tracking_code(code, "aramex")


def test_aramex_rejects_codes_of_the_wrong_shape():
    assert not valid_tracking_code("ABC", "aramex")
    assert not valid_tracking_code("https://aramex.co.nz/?l=" + CODE, "aramex")
