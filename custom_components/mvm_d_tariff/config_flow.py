from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_DISTRIBUTION_FEE,
    CONF_MERCHANT_FEE,
    CONF_TRANSMISSION_FEE,
    CONF_VAT_PERCENT,
    DEFAULT_DISTRIBUTION_FEE_HUF_KWH,
    DEFAULT_MERCHANT_FEE_HUF_KWH,
    DEFAULT_TRANSMISSION_FEE_HUF_KWH,
    DEFAULT_VAT_PERCENT,
    DOMAIN,
)


class MvmDTariffConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="MVM D tarifa", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return MvmDTariffOptionsFlow(config_entry)


class MvmDTariffOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_MERCHANT_FEE, default=options.get(CONF_MERCHANT_FEE, DEFAULT_MERCHANT_FEE_HUF_KWH)): vol.Coerce(float),
                vol.Required(CONF_TRANSMISSION_FEE, default=options.get(CONF_TRANSMISSION_FEE, DEFAULT_TRANSMISSION_FEE_HUF_KWH)): vol.Coerce(float),
                vol.Required(CONF_DISTRIBUTION_FEE, default=options.get(CONF_DISTRIBUTION_FEE, DEFAULT_DISTRIBUTION_FEE_HUF_KWH)): vol.Coerce(float),
                vol.Required(CONF_VAT_PERCENT, default=options.get(CONF_VAT_PERCENT, DEFAULT_VAT_PERCENT)): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
