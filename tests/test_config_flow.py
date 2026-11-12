"""Tests for the NZ Post config and options flow."""

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


async def test_user_flow_creates_hub_without_input(hass):
    """No account, no postcode — the entry is created straight away."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "NZ Parcel Tracker"
    assert result["options"][CONF_PARCELS] == []


async def test_second_hub_rejected(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "abort"
    # single_config_entry in the manifest aborts before the flow runs.
    assert result["reason"] == "single_instance_allowed"


def _hub(parcels: list[dict]) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
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
        menu or ["add_parcel", "remove_parcels", "settings"]
    )
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step_id}
    )


async def _add(hass, entry, carrier, code, menu=None):
    result = await _open_options_step(hass, entry, "add_parcel", menu)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CARRIER: carrier, CONF_TRACKING_CODE: code}
    )


_NO_PARCELS_MENU = ["add_parcel", "settings"]


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
