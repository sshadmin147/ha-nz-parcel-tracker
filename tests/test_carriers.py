"""Tests for the courier interface, the registry and courier independence.

The core must work with any :class:`Carrier`, so most of these tests drive it
with a fake second courier rather than NZ Post.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nz_parcel_tracker.carriers import (
    CARRIERS,
    Carrier,
    CarrierApiError,
    detect_carrier,
)
from custom_components.nz_parcel_tracker.carriers.nz_post import (
    NZPostApiError,
    NZPostCarrier,
)
from custom_components.nz_parcel_tracker.codes import valid_tracking_code
from custom_components.nz_parcel_tracker.const import (
    CONF_CARRIER,
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    CONF_PARCELS,
    CONF_TRACKING_CODE,
    DOMAIN,
    ParcelStatus,
)
from custom_components.nz_parcel_tracker.coordinator import ParcelCoordinator
from custom_components.nz_parcel_tracker.diagnostics import TO_REDACT
from custom_components.nz_parcel_tracker.parcels import build_parcel

from .helpers import make_coordinator
from .payloads import ACTIVE_CODE, active_sample

FAKE_CODE = "FK123456789"


class FakeApiError(CarrierApiError):
    carrier_name = "Fake Courier"


class FakeCarrier(Carrier):
    """A second courier with its own payload shape and code format."""

    key = "fake"
    name = "Fake Courier"
    redact_keys = frozenset({"secret_field"})

    def __init__(self) -> None:
        self.fetch = AsyncMock(side_effect=self._default_fetch)

    @classmethod
    def create(cls, session):
        return cls()

    @classmethod
    def matches_code(cls, code: str) -> bool:
        return code.startswith("FK") and len(code) >= 8

    async def _default_fetch(self, code: str) -> dict[str, Any] | None:
        return {"ref": code, "state": "delivered", "secret_field": "x"}

    async def async_get_parcel(self, tracking_code: str) -> dict[str, Any] | None:
        return await self.fetch(tracking_code)

    def prepare_raw(self, raw: dict[str, Any], tracking_code: str) -> dict[str, Any]:
        return {"ref": raw.get("ref", tracking_code), "state": raw.get("state")}

    def placeholder_raw(self, tracking_code: str) -> dict[str, Any]:
        return {"ref": tracking_code, "state": None}

    def normalize(self, raw, *, include_history: bool = False) -> dict[str, Any]:
        delivered = raw["state"] == "delivered"
        return build_parcel(
            carrier=self.name,
            barcode=raw["ref"],
            status=ParcelStatus.DELIVERED if delivered else ParcelStatus.UNKNOWN,
            raw_status=raw["state"],
            delivered=delivered,
            delivered_at="2026-04-29T01:00:00+00:00" if delivered else None,
        )


def _entry(parcels: list[dict]) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        options={
            CONF_PARCELS: parcels,
            CONF_DELIVERED_FILTER_TYPE: "parcels",
            CONF_DELIVERED_FILTER_AMOUNT: 100,
        },
    )


def _two_carriers(nz_client=None) -> tuple[FakeCarrier, dict[str, Carrier]]:
    fake = FakeCarrier()
    nz_client = nz_client or AsyncMock()
    nz_client.async_get_parcel.side_effect = lambda code: active_sample(code)
    return fake, {NZPostCarrier.key: NZPostCarrier(nz_client), fake.key: fake}


# ---------------------------------------------------------------------------
# registry and code detection
# ---------------------------------------------------------------------------


def test_registry_keys_match_each_carriers_key():
    assert CARRIERS
    assert all(key == carrier.key for key, carrier in CARRIERS.items())
    assert all(carrier.name for carrier in CARRIERS.values())


def test_detect_carrier_finds_nz_post_and_rejects_nonsense():
    assert detect_carrier("00794210392837795918") == "nz_post"
    assert detect_carrier("ABC") is None
    assert detect_carrier("") is None


def test_valid_tracking_code_can_be_limited_to_one_carrier():
    assert valid_tracking_code("EXAMPLE123456", "nz_post")
    assert not valid_tracking_code("EXAMPLE123456", "no_such_carrier")
    assert not valid_tracking_code("https://example.com/EXAMPLE123456", "nz_post")


def test_nz_post_carrier_implements_the_interface():
    carrier = NZPostCarrier(AsyncMock())
    assert carrier.key == "nz_post"
    assert carrier.name == "NZ Post"
    assert carrier.placeholder_raw("CODE") == {"tracking_reference": "CODE"}
    prepared = carrier.prepare_raw({"tracking_events": []}, "CODE")
    assert prepared["tracking_reference"] == "CODE"
    parcel = carrier.normalize(active_sample())
    assert parcel["carrier"] == "NZ Post"
    assert parcel["barcode"] == ACTIVE_CODE


def test_nz_post_api_error_is_a_carrier_api_error_and_names_the_courier():
    error = NZPostApiError("HTTP 500", status_code=500)
    assert isinstance(error, CarrierApiError)
    assert str(error) == "NZ Post API request failed: HTTP 500"
    assert error.status_code == 500


def test_build_parcel_publishes_the_same_keys_for_every_courier():
    fake_parcel = FakeCarrier().normalize({"ref": FAKE_CODE, "state": "x"})
    nz_parcel = NZPostCarrier(AsyncMock()).normalize(active_sample())
    assert list(fake_parcel) == list(nz_parcel)


def test_diagnostics_redaction_covers_every_registered_carrier():
    for carrier in CARRIERS.values():
        assert carrier.redact_keys <= TO_REDACT
    assert {"tracking_reference", "signed_by", "barcode"} <= TO_REDACT


# ---------------------------------------------------------------------------
# the coordinator with more than one courier
# ---------------------------------------------------------------------------


async def test_each_parcel_is_fetched_through_its_own_carrier(hass):
    entry = _entry(
        [
            {CONF_TRACKING_CODE: ACTIVE_CODE, CONF_CARRIER: "nz_post"},
            {CONF_TRACKING_CODE: FAKE_CODE, CONF_CARRIER: "fake"},
        ]
    )
    entry.add_to_hass(hass)
    fake, carriers = _two_carriers()
    coordinator = ParcelCoordinator(hass, carriers, entry)

    data = await coordinator._async_update_data()

    fake.fetch.assert_awaited_once_with(FAKE_CODE)
    assert [p["barcode"] for p in data] == [ACTIVE_CODE]
    assert [p["barcode"] for p in coordinator.delivered] == [FAKE_CODE]
    assert coordinator.delivered[0]["carrier"] == "Fake Courier"


async def test_parcel_without_a_stored_carrier_means_nz_post(hass):
    entry = _entry([{CONF_TRACKING_CODE: ACTIVE_CODE}])
    entry.add_to_hass(hass)
    fake, carriers = _two_carriers()
    coordinator = ParcelCoordinator(hass, carriers, entry)

    data = await coordinator._async_update_data()

    fake.fetch.assert_not_awaited()
    assert data[0]["carrier"] == "NZ Post"


async def test_unknown_carrier_is_skipped_with_a_warning(hass, caplog):
    entry = _entry(
        [
            {CONF_TRACKING_CODE: ACTIVE_CODE, CONF_CARRIER: "nz_post"},
            {CONF_TRACKING_CODE: "GONE12345", CONF_CARRIER: "removed_courier"},
        ]
    )
    entry.add_to_hass(hass)
    _, carriers = _two_carriers()
    coordinator = ParcelCoordinator(hass, carriers, entry)

    with caplog.at_level(logging.WARNING):
        data = await coordinator._async_update_data()

    assert [p["barcode"] for p in data] == [ACTIVE_CODE]
    assert "unknown courier 'removed_courier'" in caplog.text


async def test_failing_carrier_is_named_in_the_log_and_keeps_cached_data(hass, caplog):
    entry = _entry([{CONF_TRACKING_CODE: FAKE_CODE, CONF_CARRIER: "fake"}])
    entry.add_to_hass(hass)
    fake, carriers = _two_carriers()
    # Not delivered yet, so it is fetched again on the next poll.
    fake.fetch.side_effect = lambda code: {"ref": code, "state": "moving"}
    coordinator = ParcelCoordinator(hass, carriers, entry)
    await coordinator._async_update_data()  # caches the payload

    fake.fetch.side_effect = FakeApiError("HTTP 500", status_code=500)
    with caplog.at_level(logging.WARNING):
        data = await coordinator._async_update_data()

    assert "Fake Courier fetch failed" in caplog.text
    assert [p["barcode"] for p in data] == [FAKE_CODE]


async def test_unknown_to_the_courier_shows_that_couriers_placeholder(hass):
    entry = _entry([{CONF_TRACKING_CODE: FAKE_CODE, CONF_CARRIER: "fake"}])
    entry.add_to_hass(hass)
    fake, carriers = _two_carriers()
    fake.fetch.side_effect = None
    fake.fetch.return_value = None  # the courier has not scanned it yet
    coordinator = ParcelCoordinator(hass, carriers, entry)

    data = await coordinator._async_update_data()

    assert data[0]["barcode"] == FAKE_CODE
    assert data[0]["status"] is ParcelStatus.UNKNOWN


async def test_make_coordinator_helper_uses_the_nz_post_carrier(hass):
    entry = _entry([{CONF_TRACKING_CODE: ACTIVE_CODE}])
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_parcel.return_value = active_sample()
    coordinator = make_coordinator(hass, client, entry)

    assert [p["barcode"] for p in await coordinator._async_update_data()] == [
        ACTIVE_CODE
    ]


@pytest.mark.parametrize("carrier", list(CARRIERS))
def test_every_registered_carrier_can_be_created(carrier):
    instance = CARRIERS[carrier].create(AsyncMock())
    assert isinstance(instance, Carrier)
