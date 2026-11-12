"""Tests for the NZ Post config and options flow."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nz_parcel_tracker.config_flow import (
    looks_like_link,
    normalize_tracking_code,
    valid_tracking_code,
)
from custom_components.nz_parcel_tracker.const import (
    CONF_CARRIER,
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    CONF_INCLUDE_HISTORY,
    CONF_PARCELS,
    CONF_TRACKING_CODE,
    DOMAIN,
)

_CHECK_KEY = (
    "custom_components.nz_parcel_tracker.carriers.dhl.DHLCarrier.async_validate_config"
)


def test_normalize_tracking_code_strips_and_uppercases():
    assert normalize_tracking_code(" example 123-456 ") == "EXAMPLE 123-456"
    assert normalize_tracking_code("") == ""
    assert normalize_tracking_code(None) == ""


def test_valid_tracking_code_accepts_plain_references():
    assert valid_tracking_code("EXAMPLE123456", "nz_post")
    assert valid_tracking_code("00794210392837795918", "nz_post")
    assert valid_tracking_code("FX0003653338", "nz_post")
    assert valid_tracking_code("LH440267135AU", "nz_post")
    assert valid_tracking_code("UPU-RA123456789NZ", "nz_post")
    assert valid_tracking_code("example 123 456", "nz_post")
    assert valid_tracking_code("MP0085494934", "aramex")


def test_valid_tracking_code_rejects_bad_shapes():
    assert not valid_tracking_code("", "nz_post")
    assert not valid_tracking_code("ABC", "nz_post")
    assert not valid_tracking_code("A" * 31, "nz_post")
    assert not valid_tracking_code("EXAMPLE123456|SHOES", "nz_post")
    assert not valid_tracking_code("EXAMPLE_123456", "nz_post")
    assert not valid_tracking_code("EXAMPLE123456", "no_such_courier")


def test_links_are_rejected_and_detected():
    link = "https://www.trackandtrace.courierpost.co.nz/search/00894210392937491823"
    assert looks_like_link(link)
    assert looks_like_link("www.nzpost.co.nz/tools/tracking")
    assert looks_like_link(
        "HTTP://WWW.TRACKANDTRACE.COURIERPOST.CO.NZ/SEARCH/00894210392937491823"
    )
    assert not looks_like_link("00794210392837795918")
    assert not valid_tracking_code(link, "nz_post")


async def test_user_flow_offers_a_key_or_skip_and_skip_creates_the_hub(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "menu"
    assert result["menu_options"] == ["api_keys", "skip"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "skip"}
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "NZ Parcel Tracker"
    assert result["data"] == {}
    assert result["options"][CONF_PARCELS] == []


async def _open_key_step(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "api_keys"}
    )


async def test_user_flow_stores_a_valid_dhl_key(hass):
    result = await _open_key_step(hass)
    assert result["type"] == "form"
    with patch(_CHECK_KEY, new=AsyncMock(return_value=None)) as check:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"dhl_api_key": "  my-key  "}
        )
    assert result["type"] == "create_entry"
    assert result["data"] == {"dhl_api_key": "my-key"}
    check.assert_awaited_once()


@pytest.mark.parametrize("error", ["invalid_api_key", "cannot_connect"])
async def test_user_flow_rejects_a_bad_key_and_lets_you_retry(hass, error):
    result = await _open_key_step(hass)
    with patch(_CHECK_KEY, new=AsyncMock(return_value=error)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"dhl_api_key": "bad"}
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": error}
    with patch(_CHECK_KEY, new=AsyncMock(return_value=None)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"dhl_api_key": "good"}
        )
    assert result["data"] == {"dhl_api_key": "good"}


async def test_user_flow_with_a_blank_key_creates_the_hub_without_one(hass):
    result = await _open_key_step(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["data"] == {}


async def test_second_hub_rejected(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "abort"
    # single_config_entry in the manifest aborts before the flow runs.
    assert result["reason"] == "single_instance_allowed"


def _hub(parcels: list[dict], data: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data=data or {},
        options={CONF_PARCELS: parcels},
    )


def _settings_input(
    *,
    history=False,
    filter_type="days",
    amount=7,
) -> dict:
    """Build the settings-form submission."""
    return {
        CONF_DELIVERED_FILTER_TYPE: filter_type,
        CONF_DELIVERED_FILTER_AMOUNT: amount,
        CONF_INCLUDE_HISTORY: history,
    }


async def _open_options_step(hass, entry, step_id: str, menu=None):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert result["menu_options"] == (
        menu or ["add_parcel", "remove_parcels", "api_keys", "settings"]
    )
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step_id}
    )


async def _add(hass, entry, carrier, code, menu=None):
    result = await _open_options_step(hass, entry, "add_parcel", menu)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CARRIER: carrier, CONF_TRACKING_CODE: code}
    )


_NO_PARCELS_MENU = ["add_parcel", "api_keys", "settings"]


async def test_menu_hides_remove_when_nothing_is_tracked(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == _NO_PARCELS_MENU


async def test_options_add_parcel_stores_the_chosen_courier(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _add(hass, entry, "aramex", "mp0085494934", _NO_PARCELS_MENU)
    assert result["type"] == "create_entry"
    assert result["data"][CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "MP0085494934", CONF_CARRIER: "aramex"}
    ]


async def test_same_code_shape_is_never_guessed(hass):
    """The courier comes from the form, whatever the code looks like."""
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _add(hass, entry, "nz_post", "MP0085494934", _NO_PARCELS_MENU)
    assert result["data"][CONF_PARCELS][0][CONF_CARRIER] == "nz_post"


async def test_options_add_keeps_existing_parcels_and_settings(hass):
    entry = _hub([{CONF_TRACKING_CODE: "EXAMPLE111111", CONF_CARRIER: "aramex"}])
    entry.add_to_hass(hass)
    result = await _add(hass, entry, "nz_post", "example-123 456")
    assert result["data"][CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "EXAMPLE111111", CONF_CARRIER: "aramex"},
        {CONF_TRACKING_CODE: "EXAMPLE-123 456", CONF_CARRIER: "nz_post"},
    ]


async def test_options_rejects_pasted_link(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _add(
        hass,
        entry,
        "nz_post",
        "https://www.nzpost.co.nz/tools/tracking?trackid=1234567890",
        _NO_PARCELS_MENU,
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "tracking_code_is_link"}
    assert entry.options[CONF_PARCELS] == []


async def test_options_rejects_malformed_code(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _add(hass, entry, "nz_post", "ABC", _NO_PARCELS_MENU)
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_tracking_code"}


async def test_options_rejects_an_already_tracked_code(hass):
    entry = _hub([{CONF_TRACKING_CODE: "EXAMPLE111111", CONF_CARRIER: "nz_post"}])
    entry.add_to_hass(hass)
    result = await _add(hass, entry, "aramex", "example111111")
    assert result["type"] == "form"
    assert result["errors"] == {"base": "already_tracked"}


async def test_options_remove_parcel(hass):
    entry = _hub(
        [
            {CONF_TRACKING_CODE: "EXAMPLE111111", CONF_CARRIER: "nz_post"},
            {CONF_TRACKING_CODE: "EXAMPLE222222"},  # legacy: no courier stored
            {CONF_TRACKING_CODE: "EXAMPLE333333", CONF_CARRIER: "gone"},
        ]
    )
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "remove_parcels")
    labels = [
        o["label"] for o in result["data_schema"].schema["remove"].config["options"]
    ]
    assert labels == [
        "NZ Post: EXAMPLE111111",
        "NZ Post: EXAMPLE222222",
        "EXAMPLE333333",
    ]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"remove": ["EXAMPLE222222", "EXAMPLE333333"]}
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "EXAMPLE111111", CONF_CARRIER: "nz_post"}
    ]


async def test_options_changes_history_and_delivered(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "settings", _NO_PARCELS_MENU)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _settings_input(
            history=True,
            filter_type="parcels",
            amount=5,
        ),
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_INCLUDE_HISTORY] is True
    assert result["data"][CONF_DELIVERED_FILTER_TYPE] == "parcels"
    assert result["data"][CONF_DELIVERED_FILTER_AMOUNT] == 5


# ----------------------------------------------------------- DHL key options


async def test_dhl_only_offered_once_a_key_is_stored(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "add_parcel", _NO_PARCELS_MENU)
    couriers = result["data_schema"].schema[CONF_CARRIER].config["options"]
    assert "dhl" not in couriers

    keyed = _hub([], {"dhl_api_key": "k"})
    keyed.add_to_hass(hass)  # single_config_entry is not enforced for mocks
    result = await hass.config_entries.options.async_init(keyed.entry_id)
    assert result["menu_options"] == [
        "add_parcel",
        "api_keys",
        "remove_api_keys",
        "settings",
    ]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_parcel"}
    )
    couriers = result["data_schema"].schema[CONF_CARRIER].config["options"]
    assert "dhl" in couriers


async def test_options_add_and_change_the_dhl_key_reloads_the_entry(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "api_keys", _NO_PARCELS_MENU)
    with (
        patch(_CHECK_KEY, new=AsyncMock(return_value=None)),
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"dhl_api_key": "new-key"}
        )
    assert result["type"] == "create_entry"
    assert entry.data == {"dhl_api_key": "new-key"}
    reload.assert_called_once_with(entry.entry_id)


async def test_options_blank_key_keeps_the_current_one_and_does_not_reload(hass):
    entry = _hub([], {"dhl_api_key": "old"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "api_keys"}
    )
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {}
        )
    assert result["type"] == "create_entry"
    assert entry.data == {"dhl_api_key": "old"}
    reload.assert_not_called()


async def test_options_rejects_a_bad_dhl_key(hass):
    entry = _hub([], {"dhl_api_key": "old"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "api_keys"}
    )
    with patch(_CHECK_KEY, new=AsyncMock(return_value="invalid_api_key")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"dhl_api_key": "bad"}
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_api_key"}
    assert entry.data == {"dhl_api_key": "old"}


async def test_options_remove_the_dhl_key(hass):
    entry = _hub([], {"dhl_api_key": "old"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_api_keys"}
    )
    labels = [
        o["label"] for o in result["data_schema"].schema["remove"].config["options"]
    ]
    assert labels == ["DHL API key"]
    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"remove": ["dhl_api_key"]}
        )
    assert result["type"] == "create_entry"
    assert entry.data == {}
    reload.assert_called_once_with(entry.entry_id)
