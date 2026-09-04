from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import MvmDTariffCoordinator
from .cost_tracker import MvmDCostTracker

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

FRONTEND_DIR = Path(__file__).parent / "frontend"
CARD_PATH = FRONTEND_DIR / "mvm-d-tariff-card.js"
CARD_STATIC_URL = "/mvm_d_tariff/frontend/mvm-d-tariff-card.js"
CARD_URL = f"{CARD_STATIC_URL}?v=0.2.0"

_FRONTEND_JS_REGISTERED = "_frontend_js_registered"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up global MVM D tariff resources once per Home Assistant process."""

    # The static HTTP route must only be registered once per HA process.
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                CARD_STATIC_URL,
                str(CARD_PATH),
                cache_headers=False,
            )
        ]
    )

    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one MVM D tariff config entry."""

    domain_data = hass.data.setdefault(DOMAIN, {})

    # Register the Lovelace card resource once.
    # This remains available across config-entry reloads.
    if not domain_data.get(_FRONTEND_JS_REGISTERED):
        add_extra_js_url(hass, CARD_URL)
        domain_data[_FRONTEND_JS_REGISTERED] = True

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
    """Reload the config entry after options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload one config entry without unregistering global frontend resources."""

    domain_data = hass.data.get(DOMAIN, {})
    data = domain_data.get(entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok and data:
        await data["cost_tracker"].async_unload()
        domain_data.pop(entry.entry_id, None)

    return unload_ok
