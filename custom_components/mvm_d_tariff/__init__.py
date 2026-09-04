from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url, remove_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import MvmDTariffCoordinator
from .cost_tracker import MvmDCostTracker

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

FRONTEND_DIR = Path(__file__).parent / "frontend"
CARD_PATH = FRONTEND_DIR / "mvm-d-tariff-card.js"
CARD_URL = "/mvm_d_tariff/frontend/mvm-d-tariff-card.js?v=0.2.0"
CARD_STATIC_URL = "/mvm_d_tariff/frontend/mvm-d-tariff-card.js"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_STATIC_URL, str(CARD_PATH), cache_headers=False)
    ])
    add_extra_js_url(hass, CARD_URL)

    coordinator = MvmDTariffCoordinator(hass, entry)
    await coordinator.async_load_cached_forecast()
    await coordinator.async_config_entry_first_refresh()

    tracker = MvmDCostTracker(hass, entry, coordinator)
    await tracker.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "cost_tracker": tracker,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data[DOMAIN].get(entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and data:
        await data["cost_tracker"].async_unload()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    if unload_ok:
        remove_extra_js_url(hass, CARD_URL)
    return unload_ok
