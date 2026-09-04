from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_A1_PRICE,
    CONF_CHEAP_THRESHOLD,
    CONF_DISTRIBUTION_FEE,
    CONF_ENERGY_ENTITY,
    CONF_MERCHANT_FEE,
    CONF_TRANSMISSION_FEE,
    CONF_VAT_PERCENT,
    DEFAULT_A1_PRICE_HUF_KWH,
    DEFAULT_CHEAP_THRESHOLD_HUF_KWH,
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
        return MvmDTariffOptionsFlow()


class MvmDTariffOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema({
            vol.Required(
                CONF_MERCHANT_FEE,
                default=options.get(CONF_MERCHANT_FEE, DEFAULT_MERCHANT_FEE_HUF_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_TRANSMISSION_FEE,
                default=options.get(CONF_TRANSMISSION_FEE, DEFAULT_TRANSMISSION_FEE_HUF_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_DISTRIBUTION_FEE,
                default=options.get(CONF_DISTRIBUTION_FEE, DEFAULT_DISTRIBUTION_FEE_HUF_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_VAT_PERCENT,
                default=options.get(CONF_VAT_PERCENT, DEFAULT_VAT_PERCENT),
            ): vol.Coerce(float),
            vol.Required(
                CONF_A1_PRICE,
                default=options.get(CONF_A1_PRICE, DEFAULT_A1_PRICE_HUF_KWH),
            ): vol.Coerce(float),
            vol.Required(
                CONF_CHEAP_THRESHOLD,
                default=options.get(CONF_CHEAP_THRESHOLD, DEFAULT_CHEAP_THRESHOLD_HUF_KWH),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_ENERGY_ENTITY,
                default=options.get(CONF_ENERGY_ENTITY),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=Platform.SENSOR,
                    device_class=SensorDeviceClass.ENERGY,
                )
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
