"""Config flow for the NZ Parcel Tracker integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .carriers import CARRIERS, available_carriers
from .codes import looks_like_link, normalize_tracking_code, valid_tracking_code
from .const import (
    CONF_CARRIER,
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    CONF_INCLUDE_HISTORY,
    CONF_PARCELS,
    CONF_TRACKING_CODE,
    DEFAULT_CARRIER,
    DEFAULT_DELIVERED_FILTER_AMOUNT,
    DEFAULT_DELIVERED_FILTER_TYPE,
    DEFAULT_INCLUDE_HISTORY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _current_parcels(entry: ConfigEntry) -> list[dict[str, str]]:
    """Return a mutable copy of the tracked parcels list."""
    return [dict(item) for item in entry.options.get(CONF_PARCELS, [])]


def _keyed_carriers() -> dict[str, type]:
    """Couriers that need an API key, by the entry data key that holds it."""
    return {c.config_key: c for c in CARRIERS.values() if c.config_key}


def _keys_schema() -> vol.Schema:
    """One optional password field per courier that needs a key."""
    return vol.Schema(
        {
            vol.Optional(config_key): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            )
            for config_key in _keyed_carriers()
        }
    )


async def _check_keys(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[dict[str, str], dict[str, str]]:
    """Validate the keys that were filled in.

    Returns ``(accepted keys, errors)``; a blank field is simply not included.
    """
    accepted: dict[str, str] = {}
    session = async_get_clientsession(hass)
    for config_key, carrier in _keyed_carriers().items():
        value = str(user_input.get(config_key) or "").strip()
        if not value:
            continue
        error = await carrier.async_validate_config(session, value)
        if error:
            return {}, {"base": error}
        accepted[config_key] = value
    return accepted, {}


class ParcelTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI-driven configuration flow for the integration."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> ParcelTrackerOptionsFlowHandler:
        """Return the options flow handler."""
        return ParcelTrackerOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the hub — single instance, no input needed.

        Most couriers need no account, so the hub is created right away. A
        courier that needs an API key is offered here with a skip option; it can
        be added later from the options. ``single_config_entry`` in the manifest
        enforces one hub.
        """
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if not _keyed_carriers():
            return self._create_hub({})
        return self.async_show_menu(step_id="user", menu_options=["api_keys", "skip"])

    async def async_step_skip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the hub without any API keys."""
        return self._create_hub({})

    async def async_step_api_keys(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the API keys; they are checked before the hub is created."""
        errors: dict[str, str] = {}
        if user_input is not None:
            accepted, errors = await _check_keys(self.hass, user_input)
            if not errors:
                return self._create_hub(accepted)
        return self.async_show_form(
            step_id="api_keys",
            data_schema=_keys_schema(),
            errors=errors,
        )

    def _create_hub(self, data: dict[str, str]) -> ConfigFlowResult:
        return self.async_create_entry(
            title="NZ Parcel Tracker",
            data=data,
            options={
                CONF_PARCELS: [],
                CONF_DELIVERED_FILTER_TYPE: DEFAULT_DELIVERED_FILTER_TYPE,
                CONF_DELIVERED_FILTER_AMOUNT: DEFAULT_DELIVERED_FILTER_AMOUNT,
                CONF_INCLUDE_HISTORY: DEFAULT_INCLUDE_HISTORY,
            },
        )


class ParcelTrackerOptionsFlowHandler(OptionsFlow):
    """Manage tracked parcels separately from integration settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer adding or removing parcels, and the integration settings."""
        menu = ["add_parcel"]
        if _current_parcels(self.config_entry):
            menu.append("remove_parcels")
        if _keyed_carriers():
            menu.append("api_keys")
            if any(self.config_entry.data.get(k) for k in _keyed_carriers()):
                menu.append("remove_api_keys")
        menu.append("settings")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_parcel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add one parcel; the courier is always chosen, never guessed."""
        errors: dict[str, str] = {}
        if user_input is not None:
            carrier = user_input[CONF_CARRIER]
            code = normalize_tracking_code(user_input[CONF_TRACKING_CODE])
            parcels = _current_parcels(self.config_entry)
            if looks_like_link(code):
                errors["base"] = "tracking_code_is_link"
            elif not valid_tracking_code(code, carrier):
                errors["base"] = "invalid_tracking_code"
            elif any(p[CONF_TRACKING_CODE] == code for p in parcels):
                errors["base"] = "already_tracked"
            else:
                parcels.append({CONF_TRACKING_CODE: code, CONF_CARRIER: carrier})
                return self._save_parcels(parcels)
        schema = vol.Schema(
            {
                vol.Required(CONF_CARRIER): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=available_carriers(self.config_entry.data),
                        translation_key=CONF_CARRIER,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_TRACKING_CODE): selector.TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="add_parcel",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_remove_parcels(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Stop tracking the selected parcels."""
        parcels = _current_parcels(self.config_entry)
        if user_input is not None:
            remove = set(user_input.get("remove", []))
            return self._save_parcels(
                [p for p in parcels if p[CONF_TRACKING_CODE] not in remove]
            )
        options = [
            selector.SelectOptionDict(
                value=p[CONF_TRACKING_CODE],
                label=(
                    f"{CARRIERS[p.get(CONF_CARRIER, DEFAULT_CARRIER)].name}: "
                    if p.get(CONF_CARRIER, DEFAULT_CARRIER) in CARRIERS
                    else ""
                )
                + p[CONF_TRACKING_CODE],
            )
            for p in parcels
        ]
        schema = vol.Schema(
            {
                vol.Required("remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_parcels", data_schema=schema)

    async def async_step_api_keys(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add or replace API keys; a blank field keeps the current key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            accepted, errors = await _check_keys(self.hass, user_input)
            if not errors:
                return self._save_keys({**self.config_entry.data, **accepted})
        return self.async_show_form(
            step_id="api_keys", data_schema=_keys_schema(), errors=errors
        )

    async def async_step_remove_api_keys(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove stored API keys; parcels of that courier stop being tracked."""
        if user_input is not None:
            remove = set(user_input.get("remove", []))
            return self._save_keys(
                {k: v for k, v in self.config_entry.data.items() if k not in remove}
            )
        options = [
            selector.SelectOptionDict(value=config_key, label=f"{carrier.name} API key")
            for config_key, carrier in _keyed_carriers().items()
            if self.config_entry.data.get(config_key)
        ]
        schema = vol.Schema(
            {
                vol.Required("remove"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="remove_api_keys", data_schema=schema)

    def _save_keys(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Store new entry data and reload, since the couriers are built from it."""
        if data != dict(self.config_entry.data):
            self.hass.config_entries.async_update_entry(self.config_entry, data=data)
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    def _save_parcels(self, parcels: list[dict[str, str]]) -> ConfigFlowResult:
        """Save a new parcel list, keeping every other option as it is."""
        return self.async_create_entry(
            title="",
            data={
                CONF_PARCELS: parcels,
                CONF_DELIVERED_FILTER_TYPE: self.config_entry.options.get(
                    CONF_DELIVERED_FILTER_TYPE, DEFAULT_DELIVERED_FILTER_TYPE
                ),
                CONF_DELIVERED_FILTER_AMOUNT: self.config_entry.options.get(
                    CONF_DELIVERED_FILTER_AMOUNT, DEFAULT_DELIVERED_FILTER_AMOUNT
                ),
                CONF_INCLUDE_HISTORY: self.config_entry.options.get(
                    CONF_INCLUDE_HISTORY, DEFAULT_INCLUDE_HISTORY
                ),
            },
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and handle the non-parcel integration settings."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_PARCELS: _current_parcels(self.config_entry),
                    CONF_DELIVERED_FILTER_TYPE: user_input[CONF_DELIVERED_FILTER_TYPE],
                    CONF_DELIVERED_FILTER_AMOUNT: int(
                        user_input[CONF_DELIVERED_FILTER_AMOUNT]
                    ),
                    CONF_INCLUDE_HISTORY: bool(user_input[CONF_INCLUDE_HISTORY]),
                },
            )
        current = self.config_entry.options
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_DELIVERED_FILTER_TYPE,
                default=current.get(
                    CONF_DELIVERED_FILTER_TYPE, DEFAULT_DELIVERED_FILTER_TYPE
                ),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["days", "parcels"],
                    translation_key=CONF_DELIVERED_FILTER_TYPE,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                CONF_DELIVERED_FILTER_AMOUNT,
                default=current.get(
                    CONF_DELIVERED_FILTER_AMOUNT, DEFAULT_DELIVERED_FILTER_AMOUNT
                ),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=365, step=1, mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_INCLUDE_HISTORY,
                default=current.get(CONF_INCLUDE_HISTORY, DEFAULT_INCLUDE_HISTORY),
            ): selector.BooleanSelector(),
        }
        return self.async_show_form(step_id="settings", data_schema=vol.Schema(schema))
