"""Tests for the NZ Post services (track_parcel / untrack_parcel)."""

from unittest.mock import AsyncMock, patch

from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.nz_parcel_tracker.const import (
    CONF_CARRIER,
    CONF_PARCELS,
    CONF_TRACKING_CODE,
    DOMAIN,
)

from .payloads import active_sample

_SAMPLE = active_sample()


async def _setup(hass, parcels: list[dict] | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        options={CONF_PARCELS: parcels or []},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.nz_parcel_tracker.carriers.nz_post.api.NZPostApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_track_parcel_adds_to_options(hass):
    entry = await _setup(hass)
    with patch(
        "custom_components.nz_parcel_tracker.carriers.nz_post.api.NZPostApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999", CONF_CARRIER: "nz_post"},
            blocking=True,
        )
        await hass.async_block_till_done()

    parcels = entry.options[CONF_PARCELS]
    assert parcels == [{CONF_TRACKING_CODE: "EXAMPLE999999", CONF_CARRIER: "nz_post"}]


async def test_track_parcel_normalizes_code(hass):
    entry = await _setup(hass)
    with patch(
        "custom_components.nz_parcel_tracker.carriers.nz_post.api.NZPostApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "example-999 999", CONF_CARRIER: "nz_post"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert entry.options[CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "EXAMPLE-999 999", CONF_CARRIER: "nz_post"}
    ]


async def test_track_parcel_rejects_blank_code(hass):
    await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "", CONF_CARRIER: "nz_post"},
            blocking=True,
        )


async def test_track_parcel_rejects_pasted_link(hass):
    entry = await _setup(hass)
    link = "https://www.trackandtrace.courierpost.co.nz/search/00894210392937491823"
    with pytest.raises(ServiceValidationError, match="web address"):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: link, CONF_CARRIER: "nz_post"},
            blocking=True,
        )
    assert entry.options[CONF_PARCELS] == []


async def test_track_parcel_rejects_malformed_code(hass):
    entry = await _setup(hass)
    with pytest.raises(
        ServiceValidationError, match="not a valid tracking code for NZ Post"
    ):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "ABC", CONF_CARRIER: "nz_post"},
            blocking=True,
        )
    assert entry.options[CONF_PARCELS] == []


async def test_track_parcel_duplicate_is_noop(hass):
    entry = await _setup(hass)
    with patch(
        "custom_components.nz_parcel_tracker.carriers.nz_post.api.NZPostApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        for _ in range(2):
            await hass.services.async_call(
                DOMAIN,
                "track_parcel",
                {CONF_TRACKING_CODE: "EXAMPLE999999", CONF_CARRIER: "nz_post"},
                blocking=True,
            )
            await hass.async_block_till_done()

    assert len(entry.options[CONF_PARCELS]) == 1


async def test_untrack_parcel_removes_from_options(hass):
    entry = await _setup(hass, parcels=[{CONF_TRACKING_CODE: "EXAMPLE999999"}])
    with patch(
        "custom_components.nz_parcel_tracker.carriers.nz_post.api.NZPostApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "untrack_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert entry.options[CONF_PARCELS] == []


async def test_untrack_unknown_code_is_noop(hass):
    entry = await _setup(hass, parcels=[{CONF_TRACKING_CODE: "EXAMPLE999999"}])
    with patch(
        "custom_components.nz_parcel_tracker.carriers.nz_post.api.NZPostApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "untrack_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE000000"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert len(entry.options[CONF_PARCELS]) == 1


async def test_track_parcel_requires_a_courier(hass):
    entry = await _setup(hass)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999"},
            blocking=True,
        )
    assert entry.options[CONF_PARCELS] == []


async def test_track_parcel_rejects_an_unknown_courier(hass):
    await _setup(hass)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999", CONF_CARRIER: "nope"},
            blocking=True,
        )


async def test_track_parcel_refuses_dhl_without_a_key(hass):
    entry = await _setup(hass)
    with pytest.raises(ServiceValidationError, match="needs an API key"):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "1234567890", CONF_CARRIER: "dhl"},
            blocking=True,
        )
    assert entry.options[CONF_PARCELS] == []


async def test_track_parcel_accepts_dhl_with_a_key(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={"dhl_api_key": "k"},
        options={CONF_PARCELS: []},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.nz_parcel_tracker.carriers.dhl.DHLApiClient.async_get_parcel",
            new=AsyncMock(return_value=None),
        ),
        patch.object(hass.config_entries, "async_schedule_reload"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "1234567890", CONF_CARRIER: "dhl"},
            blocking=True,
        )
    assert entry.options[CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "1234567890", CONF_CARRIER: "dhl"}
    ]


async def test_track_parcel_stores_the_chosen_courier(hass):
    entry = await _setup(hass)
    await hass.services.async_call(
        DOMAIN,
        "track_parcel",
        {CONF_TRACKING_CODE: "mp0085494934", CONF_CARRIER: "aramex"},
        blocking=True,
    )
    assert entry.options[CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "MP0085494934", CONF_CARRIER: "aramex"}
    ]
