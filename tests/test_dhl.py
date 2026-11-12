"""Tests for the DHL courier: API client, throttling, mapping, availability."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.nz_parcel_tracker.carriers import (
    CARRIERS,
    CarrierApiError,
    available_carriers,
    create_carriers,
)
from custom_components.nz_parcel_tracker.carriers.dhl import (
    DHLApiClient,
    DHLApiError,
    DHLCarrier,
)
from custom_components.nz_parcel_tracker.carriers.dhl.mapping import (
    map_status_code,
    normalize_parcel,
    sanitize_shipment,
)
from custom_components.nz_parcel_tracker.codes import valid_tracking_code
from custom_components.nz_parcel_tracker.const import ParcelStatus
from custom_components.nz_parcel_tracker.device import ATTRIBUTION

CODE = "1234567890"


def _event(when: str, code: str, text: str) -> dict:
    return {
        "timestamp": when,
        "statusCode": code,
        "status": text,
        "description": "free text that may name a place or person",
        "location": {"address": {"addressLocality": "Somewhere"}},
    }


def _shipment(code="transit", text="IN TRANSIT", events=None, **extra) -> dict:
    return {
        "id": CODE,
        "service": "express",
        "origin": {"address": {"addressLocality": "Leipzig"}},
        "destination": {"address": {"addressLocality": "Auckland"}},
        "status": {
            "timestamp": "2026-11-10T08:00:00",
            "statusCode": code,
            "status": text,
            "description": "free text",
        },
        "events": events or [],
        **extra,
    }


def _session(status: int, body=None, headers=None, raises=None) -> MagicMock:
    response = AsyncMock()
    response.status = status
    response.headers = headers or {}
    if isinstance(body, Exception):
        response.json = AsyncMock(side_effect=body)
    else:
        response.json = AsyncMock(return_value=body)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx, side_effect=raises)
    return session


def _client(session, gap=0) -> DHLApiClient:
    return DHLApiClient(session, "secret-key", min_gap=gap)


# --------------------------------------------------------------------- client


async def test_client_sends_the_key_header_and_returns_the_shipment():
    session = _session(200, {"shipments": [_shipment()]})
    shipment = await _client(session).async_get_parcel(CODE)

    assert shipment["id"] == CODE
    kwargs = session.get.call_args.kwargs
    assert kwargs["headers"]["DHL-API-Key"] == "secret-key"
    assert kwargs["params"] == {"trackingNumber": CODE, "language": "en"}
    assert "api-eu.dhl.com" in session.get.call_args.args[0]


async def test_client_prefers_the_shipment_matching_the_code():
    other = {**_shipment(), "id": "OTHER00000"}
    session = _session(200, {"shipments": [other, _shipment()]})
    assert (await _client(session).async_get_parcel(CODE))["id"] == CODE
    session = _session(200, {"shipments": [other]})
    assert (await _client(session).async_get_parcel(CODE))["id"] == "OTHER00000"


@pytest.mark.parametrize("body", [{"shipments": []}, {}, {"shipments": ["junk"]}])
async def test_client_returns_none_without_a_shipment(body):
    assert await _client(_session(200, body)).async_get_parcel(CODE) is None


async def test_client_treats_404_as_unknown():
    assert await _client(_session(404)).async_get_parcel(CODE) is None


@pytest.mark.parametrize("status", [401, 403])
async def test_client_flags_a_rejected_key(status):
    with pytest.raises(DHLApiError, match="rejected the API key") as err:
        await _client(_session(status)).async_get_parcel(CODE)
    assert err.value.status_code == status
    assert isinstance(err.value, CarrierApiError)
    assert "secret-key" not in str(err.value)


@pytest.mark.parametrize(
    ("header", "expected"), [("30", 30.0), ("-5", 0.0), ("junk", None), (None, None)]
)
async def test_client_reads_retry_after_on_429(header, expected):
    headers = {"Retry-After": header} if header else {}
    with pytest.raises(DHLApiError) as err:
        await _client(_session(429, None, headers)).async_get_parcel(CODE)
    assert err.value.status_code == 429
    assert err.value.retry_after == expected


async def test_client_reads_a_retry_after_http_date():
    headers = {"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}
    with pytest.raises(DHLApiError) as err:
        await _client(_session(429, None, headers)).async_get_parcel(CODE)
    assert err.value.retry_after > 0


async def test_client_raises_on_other_errors_and_bad_bodies():
    with pytest.raises(DHLApiError, match="HTTP 500"):
        await _client(_session(500)).async_get_parcel(CODE)
    with pytest.raises(DHLApiError, match="unparseable"):
        await _client(_session(200, ValueError("x"))).async_get_parcel(CODE)
    with pytest.raises(DHLApiError, match="not a JSON object"):
        await _client(_session(200, ["x"])).async_get_parcel(CODE)


async def test_client_propagates_network_errors():
    session = _session(200, raises=aiohttp.ClientError("boom"))
    with pytest.raises(aiohttp.ClientError):
        await _client(session).async_get_parcel(CODE)


async def test_calls_are_spaced_by_the_minimum_gap(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(
        "custom_components.nz_parcel_tracker.carriers.dhl.api.asyncio.sleep",
        fake_sleep,
    )
    client = DHLApiClient(_session(404), "k", min_gap=5.0)
    await client.async_get_parcel(CODE)
    assert sleeps == []  # the first call is not delayed
    await client.async_get_parcel(CODE)
    assert len(sleeps) == 1
    assert 0 < sleeps[0] <= 5.0


@pytest.mark.parametrize(
    ("status", "result"),
    [
        (404, None),
        (200, None),
        (401, "invalid_api_key"),
        (403, "invalid_api_key"),
        (500, "cannot_connect"),
        (429, "cannot_connect"),
    ],
)
async def test_check_key(status, result):
    body = {} if status == 200 else None
    assert await _client(_session(status, body)).async_check_key() == result


async def test_check_key_reports_connection_problems():
    session = _session(200, raises=aiohttp.ClientError("down"))
    assert await _client(session).async_check_key() == "cannot_connect"
    session = _session(200, ValueError("x"))
    assert await _client(session).async_check_key() == "cannot_connect"


async def test_carrier_validates_a_key_through_the_client():
    assert await DHLCarrier.async_validate_config(_session(404), "key") is None
    assert (
        await DHLCarrier.async_validate_config(_session(401), "key")
        == "invalid_api_key"
    )


# -------------------------------------------------------------------- mapping


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("pre-transit", ParcelStatus.REGISTERED),
        ("transit", ParcelStatus.IN_TRANSIT),
        ("delivered", ParcelStatus.DELIVERED),
        ("failure", ParcelStatus.PROBLEM),
        ("unknown", ParcelStatus.UNKNOWN),
        (None, ParcelStatus.UNKNOWN),
        ("", ParcelStatus.UNKNOWN),
    ],
)
def test_status_codes(code, status):
    assert map_status_code(code) is status


def test_unrecognised_status_code_warns_once(caplog):
    with caplog.at_level(logging.WARNING):
        assert map_status_code("brand-new") is ParcelStatus.UNKNOWN
        assert map_status_code("brand-new") is ParcelStatus.UNKNOWN
    assert caplog.text.count("Unrecognised DHL status") == 1


def test_sanitize_drops_addresses_and_free_text():
    shipment = _shipment(
        events=[_event("2026-11-10T08:00:00", "transit", "IN TRANSIT"), "junk"]
    )
    clean = sanitize_shipment({**shipment, "tracking_code": CODE})
    text = str(clean)
    assert "Leipzig" not in text
    assert "Auckland" not in text
    assert "Somewhere" not in text
    assert "free text" not in text
    assert clean["events"] == [
        {
            "timestamp": "2026-11-10T08:00:00",
            "statusCode": "transit",
            "status": "IN TRANSIT",
        }
    ]


def _normalize(shipment, **kwargs):
    return normalize_parcel({**shipment, "tracking_code": CODE}, **kwargs)


def test_normalize_in_transit_with_a_delivery_window_and_weight():
    shipment = _shipment(
        estimatedDeliveryTimeFrame={
            "estimatedFrom": "2026-11-12T09:00:00+13:00",
            "estimatedThrough": "2026-11-12T17:00:00+13:00",
        },
        details={"weight": {"value": 2500, "unitText": "g"}},
    )
    parcel = _normalize(shipment)
    assert parcel["carrier"] == "DHL"
    assert parcel["barcode"] == CODE
    assert parcel["status"] is ParcelStatus.IN_TRANSIT
    assert parcel["raw_status"] == "IN TRANSIT"
    assert parcel["delivered"] is False
    assert parcel["planned_from"] == "2026-11-12T09:00:00+13:00"
    assert parcel["planned_to"] == "2026-11-12T17:00:00+13:00"
    assert parcel["weight"] == 2.5
    assert parcel["history"] is None
    assert parcel["url"] is None


def test_normalize_uses_a_single_estimated_time_as_the_window():
    parcel = _normalize(_shipment(estimatedTimeOfDelivery="2026-11-12T12:00:00"))
    assert parcel["planned_from"] == parcel["planned_to"] == "2026-11-12T12:00:00"


def test_normalize_delivered_clears_the_window_and_uses_the_delivery_event():
    shipment = _shipment(
        "delivered",
        "DELIVERED",
        events=[
            _event("2026-11-11T14:00:00", "delivered", "DELIVERED"),
            _event("2026-11-10T08:00:00", "transit", "IN TRANSIT"),
        ],
        estimatedTimeOfDelivery="2026-11-12T12:00:00",
    )
    parcel = _normalize(shipment)
    assert parcel["status"] is ParcelStatus.DELIVERED
    assert parcel["delivered"] is True
    assert parcel["delivered_at"] == "2026-11-11T14:00:00"
    assert parcel["planned_from"] is None


def test_delivered_falls_back_to_the_status_timestamp():
    parcel = _normalize(_shipment("delivered", "DELIVERED"))
    assert parcel["delivered_at"] == "2026-11-10T08:00:00"


def test_history_is_oldest_first_and_opt_in():
    shipment = _shipment(
        events=[
            _event("2026-11-11T14:00:00", "delivered", "DELIVERED"),
            _event("2026-11-10T08:00:00", "transit", "IN TRANSIT"),
            {"statusCode": "transit"},  # no timestamp: skipped
        ]
    )
    parcel = _normalize(shipment, include_history=True)
    assert [h["raw_status"] for h in parcel["history"]] == ["IN TRANSIT", "DELIVERED"]
    assert parcel["history"][1]["status"] is ParcelStatus.DELIVERED


@pytest.mark.parametrize(
    "details",
    [
        {"weight": {"value": 2, "unitText": "stone"}},
        {"weight": {"value": "heavy", "unitText": "kg"}},
        {"weight": {"value": True, "unitText": "kg"}},
        {"weight": "2 kg"},
        {},
    ],
)
def test_unusable_weights_are_left_empty(details):
    assert _normalize(_shipment(details=details))["weight"] is None


def test_a_number_dhl_does_not_know_is_unknown():
    parcel = normalize_parcel({"tracking_code": CODE})
    assert parcel["status"] is ParcelStatus.UNKNOWN
    assert parcel["barcode"] == CODE
    assert parcel["raw_status"] is None


# -------------------------------------------------------------------- carrier


def test_dhl_is_only_available_with_a_key():
    assert DHLCarrier.available({"dhl_api_key": "k"})
    assert not DHLCarrier.available({})
    assert not DHLCarrier.available({"dhl_api_key": ""})
    assert "dhl" not in available_carriers({})
    assert "dhl" in available_carriers({"dhl_api_key": "k"})
    assert {"nz_post", "aramex", "post_haste"} <= set(available_carriers({}))


def test_create_carriers_leaves_dhl_out_without_a_key():
    assert "dhl" not in create_carriers(MagicMock(), {})
    carriers = create_carriers(MagicMock(), {"dhl_api_key": "k"})
    assert isinstance(carriers["dhl"], DHLCarrier)


def test_dhl_attribution_is_shown_on_every_entity():
    assert "Deutsche Post DHL Group" in ATTRIBUTION
    assert "couriers' public tracking services" in ATTRIBUTION


def test_dhl_redacts_the_key_and_its_id():
    assert {"dhl_api_key", "id"} <= DHLCarrier.redact_keys
    assert "dhl" in CARRIERS


@pytest.mark.parametrize("code", ["1234567890", "JJD014600006281234567", "GM12345678"])
def test_valid_dhl_codes(code):
    assert valid_tracking_code(code, "dhl")


@pytest.mark.parametrize("code", ["12345", "1234 5", "https://dhl.com/1234567890"])
def test_invalid_dhl_codes(code):
    assert not valid_tracking_code(code, "dhl")


async def test_carrier_round_trip_through_prepare_and_normalize():
    client = AsyncMock()
    client.async_get_parcel.return_value = _shipment(
        events=[_event("2026-11-10T08:00:00", "transit", "IN TRANSIT")]
    )
    carrier = DHLCarrier(client)
    raw = await carrier.async_get_parcel(CODE)
    prepared = carrier.prepare_raw(raw, CODE)
    parcel = carrier.normalize(prepared)
    assert parcel["barcode"] == CODE
    assert "Leipzig" not in str(prepared)
    assert carrier.placeholder_raw(CODE) == {"tracking_code": CODE}


def test_create_uses_the_key_from_the_entry_data():
    carrier = DHLCarrier.create(MagicMock(), {"dhl_api_key": "k"})
    assert isinstance(carrier, DHLCarrier)
