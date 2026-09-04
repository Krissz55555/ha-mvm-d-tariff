from __future__ import annotations

from statistics import mean

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_A1_PRICE, DEFAULT_A1_PRICE_HUF_KWH, DOMAIN
from .coordinator import MvmDTariffCoordinator
from .cost_tracker import MvmDCostTracker


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="MVM D tarifa",
        manufacturer="Kocsis Krisztián",
        model="MVM D tarifa kalkulátor",
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator: MvmDTariffCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    tracker: MvmDCostTracker = hass.data[DOMAIN][entry.entry_id]["cost_tracker"]
    entities: list[SensorEntity] = [
        MvmDCurrentPriceSensor(coordinator, entry),
        MvmDHupxRawPriceSensor(coordinator, entry),
        MvmDTodayForecastSensor(coordinator, entry),
        MvmDForecastMinSensor(coordinator, entry),
        MvmDForecastMaxSensor(coordinator, entry),
        MvmDForecastAverageSensor(coordinator, entry),
    ]
    if tracker.entity_id:
        entities.extend([
            MvmDMonthlyEnergySensor(tracker, entry),
            MvmDMonthlyCostSensor(tracker, entry),
            MvmDA1MonthlyCostSensor(tracker, entry),
            MvmDMonthlyDifferenceSensor(tracker, entry),
        ])
    async_add_entities(entities)


class BaseMvmSensor(CoordinatorEntity[MvmDTariffCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: MvmDTariffCoordinator, entry: ConfigEntry, suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = _device_info(entry)


class MvmDCurrentPriceSensor(BaseMvmSensor):
    _attr_name = "D tarifa Aktuális teljes ár (becs.)"
    _attr_native_unit_of_measurement = "Ft/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "current_total_price")

    @property
    def native_value(self):
        return self.coordinator.data.price_huf_kwh_gross if self.coordinator.data else None

    @property
    def extra_state_attributes(self):
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


class MvmDHupxRawPriceSensor(BaseMvmSensor):
    _attr_name = "D tarifa HUPX nyers ár"
    _attr_native_unit_of_measurement = "Ft/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "hupx_raw_price_huf_kwh")

    @property
    def native_value(self):
        return self.coordinator.data.hupx_huf_kwh_net if self.coordinator.data else None

    @property
    def extra_state_attributes(self):
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


class MvmDTodayForecastSensor(BaseMvmSensor):
    _attr_name = "D tarifa Mai előrejelzett ár"
    _attr_native_unit_of_measurement = "Ft/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "today_forecast")

    @property
    def native_value(self):
        data = self.coordinator.data
        if not data or not data.forecast:
            return None
        now_iso = self.hass.config.time_zone
        # The current interval price is already the authoritative day-ahead value.
        return data.price_huf_kwh_gross

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        if not data:
            return {}
        tomorrow_values = [p.d_price_huf_kwh_gross for p in data.tomorrow_forecast]
        return {
            "forecast_date": data.forecast_date,
            "source": "day-ahead (DAM)",
            "source_generated_at": data.forecast_generated_at,
            "fallback": data.forecast_is_fallback,
            "points": len(data.forecast),
            "forecast": [
                {
                    "start": p.timestamp,
                    "price_huf_kwh": p.d_price_huf_kwh_gross,
                    "hupx_huf_kwh": p.hupx_huf_kwh_net,
                    "hupx_eur_mwh": p.hupx_eur_mwh,
                }
                for p in data.forecast
            ],
            "tomorrow_available": bool(data.tomorrow_forecast),
            "tomorrow_forecast_date": data.tomorrow_forecast_date,
            "tomorrow_source_generated_at": data.tomorrow_forecast_generated_at,
            "tomorrow_fallback": data.tomorrow_forecast_is_fallback,
            "tomorrow_points": len(data.tomorrow_forecast),
            "tomorrow_min_huf_kwh": round(min(tomorrow_values), 2) if tomorrow_values else None,
            "tomorrow_max_huf_kwh": round(max(tomorrow_values), 2) if tomorrow_values else None,
            "tomorrow_avg_huf_kwh": round(mean(tomorrow_values), 2) if tomorrow_values else None,
            "tomorrow_forecast": [
                {
                    "start": p.timestamp,
                    "price_huf_kwh": p.d_price_huf_kwh_gross,
                    "hupx_huf_kwh": p.hupx_huf_kwh_net,
                    "hupx_eur_mwh": p.hupx_eur_mwh,
                }
                for p in data.tomorrow_forecast
            ],
        }


class _ForecastStatSensor(BaseMvmSensor):
    _attr_native_unit_of_measurement = "Ft/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    stat = "avg"

    @property
    def native_value(self):
        data = self.coordinator.data
        if not data or not data.forecast:
            return None
        values = [p.d_price_huf_kwh_gross for p in data.forecast]
        if self.stat == "min":
            return round(min(values), 2)
        if self.stat == "max":
            return round(max(values), 2)
        return round(mean(values), 2)


class MvmDForecastMinSensor(_ForecastStatSensor):
    _attr_name = "D tarifa Mai minimum előrejelzett ár"
    stat = "min"
    def __init__(self, coordinator, entry): super().__init__(coordinator, entry, "today_forecast_min")


class MvmDForecastMaxSensor(_ForecastStatSensor):
    _attr_name = "D tarifa Mai maximum előrejelzett ár"
    stat = "max"
    def __init__(self, coordinator, entry): super().__init__(coordinator, entry, "today_forecast_max")


class MvmDForecastAverageSensor(_ForecastStatSensor):
    _attr_name = "D tarifa Mai átlagos előrejelzett ár"
    stat = "avg"
    def __init__(self, coordinator, entry): super().__init__(coordinator, entry, "today_forecast_avg")


class BaseCostSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:cash"

    def __init__(self, tracker: MvmDCostTracker, entry: ConfigEntry, suffix: str) -> None:
        self.tracker = tracker
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = _device_info(entry)
        self._unsub_tracker = None

    async def async_added_to_hass(self) -> None:
        @callback
        def _updated() -> None:
            self.async_write_ha_state()
        self._unsub_tracker = self.tracker.async_add_listener(_updated)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_tracker:
            self._unsub_tracker()
            self._unsub_tracker = None

    @property
    def extra_state_attributes(self):
        return {
            "month": self.tracker.state.month,
            "source_energy_entity": self.tracker.entity_id,
            "rezsicsokkentett_keret": "nincs figyelembe véve",
        }


class MvmDMonthlyEnergySensor(BaseCostSensor):
    _attr_name = "D tarifa Havi mért fogyasztás"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    def __init__(self, tracker, entry): super().__init__(tracker, entry, "monthly_energy")
    @property
    def native_value(self): return round(self.tracker.state.energy_kwh, 3)


class MvmDMonthlyCostSensor(BaseCostSensor):
    _attr_name = "D tarifa Havi költség (becs.)"
    _attr_native_unit_of_measurement = "Ft"
    _attr_state_class = SensorStateClass.TOTAL
    def __init__(self, tracker, entry): super().__init__(tracker, entry, "monthly_d_cost")
    @property
    def native_value(self): return round(self.tracker.state.d_cost_huf, 2)


class MvmDA1MonthlyCostSensor(BaseCostSensor):
    _attr_name = "A1 tarifa Havi költség"
    _attr_native_unit_of_measurement = "Ft"
    _attr_state_class = SensorStateClass.TOTAL
    def __init__(self, tracker, entry):
        super().__init__(tracker, entry, "monthly_a1_cost")
        self.a1_price = float(entry.options.get(CONF_A1_PRICE, DEFAULT_A1_PRICE_HUF_KWH))
    @property
    def native_value(self): return round(self.tracker.state.a1_cost_huf, 2)
    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        attrs["a1_reference_price_huf_kwh"] = self.a1_price
        return attrs


class MvmDMonthlyDifferenceSensor(BaseCostSensor):
    _attr_name = "D tarifa Havi különbség az A1-hez képest"
    _attr_native_unit_of_measurement = "Ft"
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, tracker, entry): super().__init__(tracker, entry, "monthly_difference_vs_a1")
    @property
    def native_value(self):
        return round(self.tracker.state.d_cost_huf - self.tracker.state.a1_cost_huf, 2)
