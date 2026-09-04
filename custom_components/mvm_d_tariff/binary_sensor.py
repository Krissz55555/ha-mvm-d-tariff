from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CHEAP_THRESHOLD, DEFAULT_CHEAP_THRESHOLD_HUF_KWH, DOMAIN
from .coordinator import MvmDTariffCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: MvmDTariffCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([MvmDCheapPeriodBinarySensor(coordinator, entry)])


class MvmDCheapPeriodBinarySensor(CoordinatorEntity[MvmDTariffCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "D tarifa Olcsó időszak"
    _attr_icon = "mdi:cash-check"

    def __init__(self, coordinator: MvmDTariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_cheap_period"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="MVM D tarifa",
            manufacturer="Kocsis Krisztián",
            model="MVM D tarifa kalkulátor",
        )

    @property
    def threshold(self) -> float:
        return float(self.entry.options.get(CONF_CHEAP_THRESHOLD, DEFAULT_CHEAP_THRESHOLD_HUF_KWH))

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.price_huf_kwh_gross < self.threshold

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "threshold_huf_kwh": self.threshold,
            "current_price_huf_kwh": data.price_huf_kwh_gross if data else None,
            "condition": "ON, ha az aktuális becsült D tarifa a beállított határérték alatt van",
        }
