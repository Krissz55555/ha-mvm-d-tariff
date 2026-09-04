from __future__ import annotations

from dataclasses import dataclass, asdict
import logging
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_A1_PRICE,
    CONF_ENERGY_ENTITY,
    DEFAULT_A1_PRICE_HUF_KWH,
)
from .coordinator import MvmDTariffCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class CostState:
    month: str
    last_energy_kwh: float | None = None
    energy_kwh: float = 0.0
    d_cost_huf: float = 0.0
    a1_cost_huf: float = 0.0


class MvmDCostTracker:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, coordinator: MvmDTariffCoordinator) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.entity_id: str | None = entry.options.get(CONF_ENERGY_ENTITY)
        self._store: Store[dict] = Store(hass, 1, f"{entry.entry_id}_mvm_d_tariff_costs")
        self.state = CostState(month=self._month_key())
        self._unsub = None
        self._listeners: list[Callable[[], None]] = []

    def _month_key(self) -> str:
        return dt_util.now().strftime("%Y-%m")

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            try:
                self.state = CostState(**stored)
            except TypeError:
                pass
        self._ensure_month()
        if not self.entity_id:
            return
        current = self.hass.states.get(self.entity_id)
        current_kwh = self._state_to_kwh(current)
        if self.state.last_energy_kwh is None and current_kwh is not None:
            self.state.last_energy_kwh = current_kwh
            await self._save()
        self._unsub = async_track_state_change_event(self.hass, [self.entity_id], self._async_state_changed)

    async def async_unload(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        await self._save()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        @callback
        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)
        return _remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def _ensure_month(self) -> None:
        month = self._month_key()
        if self.state.month != month:
            self.state = CostState(month=month, last_energy_kwh=self.state.last_energy_kwh)

    def _state_to_kwh(self, state: State | None) -> float | None:
        if state is None or state.state in ("unknown", "unavailable", "none", ""):
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        unit = state.attributes.get("unit_of_measurement")
        if unit == UnitOfEnergy.WATT_HOUR or unit == "Wh":
            return value / 1000.0
        if unit == UnitOfEnergy.KILO_WATT_HOUR or unit == "kWh":
            return value
        if unit == UnitOfEnergy.MEGA_WATT_HOUR or unit == "MWh":
            return value * 1000.0
        _LOGGER.warning("Selected energy sensor %s has unsupported unit: %s", self.entity_id, unit)
        return None

    async def _async_state_changed(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        current_kwh = self._state_to_kwh(new_state)
        if current_kwh is None:
            return

        self._ensure_month()
        previous = self.state.last_energy_kwh
        if previous is None:
            self.state.last_energy_kwh = current_kwh
            await self._save()
            return

        delta = current_kwh - previous
        if delta < 0:
            # total_increasing meter reset / replacement
            delta = current_kwh if current_kwh >= 0 else 0
        if delta <= 0:
            self.state.last_energy_kwh = current_kwh
            return

        data = self.coordinator.data
        if data is None:
            # Keep the old baseline; the next valid reading will include this delta.
            return

        a1_price = float(self.entry.options.get(CONF_A1_PRICE, DEFAULT_A1_PRICE_HUF_KWH))
        self.state.energy_kwh += delta
        self.state.d_cost_huf += delta * data.price_huf_kwh_gross
        self.state.a1_cost_huf += delta * a1_price
        self.state.last_energy_kwh = current_kwh
        await self._save()
        self._notify()

    async def _save(self) -> None:
        await self._store.async_save(asdict(self.state))
