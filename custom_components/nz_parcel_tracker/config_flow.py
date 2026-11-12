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
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .carriers import CARRIERS
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

        Tracking is keyed on the tracking code alone (no account, no postal
        code), so there is nothing to ask at setup: the entry is created
        straight away and parcels are added afterwards via the options flow,
        the ``nz_parcel_tracker.track_parcel`` service or a dashboard button.
        ``single_config_entry`` in the manifest enforces one hub.

        """
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="NZ Parcel Tracker",
            data={},
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
                        options=list(CARRIERS),
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
