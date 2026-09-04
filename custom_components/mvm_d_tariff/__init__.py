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

_FRONTEND_STATIC_REGISTERED = "_frontend_static_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})

    # The aiohttp static route cannot be removed during a config-entry reload.
    # Register it only once for the lifetime of the Home Assistant process.
    if not domain_data.get(_FRONTEND_STATIC_REGISTERED):
        await hass.http.async_register_static_paths([
            StaticPathConfig(CARD_STATIC_URL, str(CARD_PATH), cache_headers=False)
        ])
        domain_data[_FRONTEND_STATIC_REGISTERED] = True

    # This frontend resource may be removed/re-added on config-entry reload.
    add_extra_js_url(hass, CARD_URL)

    coordinator = MvmDTariffCoordinator(hass, entry)
    await coordinator.async_load_cached_forecast()
    await coordinator.async_config_entry_first_refresh()

    tracker = MvmDCostTracker(hass, entry, coordinator)
    await tracker.async_setup()

    domain_data[entry.entry_id] = {
        "coordinator": coordinator,
        "cost_tracker": tracker,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.get(DOMAIN, {})
    data = domain_data.get(entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and data:
        await data["cost_tracker"].async_unload()
        domain_data.pop(entry.entry_id, None)

    if unload_ok:
        remove_extra_js_url(hass, CARD_URL)

    return unload_ok
