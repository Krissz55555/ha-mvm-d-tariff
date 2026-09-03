from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MvmDTariffCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: MvmDTariffCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        MvmDCurrentPriceSensor(coordinator, entry),
        MvmDHupxRawPriceSensor(coordinator, entry),
    ])


class MvmDCurrentPriceSensor(CoordinatorEntity[MvmDTariffCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "D tarifa – Aktuális teljes ár (becs.)"
    _attr_native_unit_of_measurement = "Ft/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: MvmDTariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_total_price"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="MVM D tarifa",
            manufacturer="Community integration",
            model="Dynamic tariff calculator",
        )

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.price_huf_kwh_gross if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "hupx_eur_mwh": data.hupx_eur_mwh,
            "hupx_net_huf_kwh": data.hupx_huf_kwh_net,
            "mnb_eur_huf": data.eur_huf,
            "merchant_fee_net_huf_kwh": data.merchant_fee_huf_kwh_net,
            "transmission_fee_net_huf_kwh": data.transmission_fee_huf_kwh_net,
            "distribution_fee_net_huf_kwh": data.distribution_fee_huf_kwh_net,
            "vat_percent": data.vat_percent,
            "interval_start": data.interval_start,
            "valid_until": data.valid_until,
            "source_generated_at": data.source_generated_at,
            "scope": "D tarifa – kedvezményes sávhatár feletti becsült bruttó változó költség",
        }


class MvmDHupxRawPriceSensor(CoordinatorEntity[MvmDTariffCoordinator], SensorEntity):
    """Current raw HUPX day-ahead price converted to HUF/kWh."""

    _attr_has_entity_name = True
    _attr_name = "D tarifa – HUPX nyers ár"
    _attr_native_unit_of_measurement = "Ft/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: MvmDTariffCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_hupx_raw_price_huf_kwh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="MVM D tarifa",
            manufacturer="Community integration",
            model="Dynamic tariff calculator",
        )

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.hupx_huf_kwh_net if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "hupx_eur_mwh": data.hupx_eur_mwh,
            "mnb_eur_huf": data.eur_huf,
            "interval_start": data.interval_start,
            "valid_until": data.valid_until,
            "source_generated_at": data.source_generated_at,
            "scope": "Nyers HUPX ár Ft/kWh-ra átszámítva; MVM díjak, RHD és ÁFA nélkül",
        }
