"""Overwatch NVR: every Overwatch camera as a Home Assistant camera, with live video."""

from __future__ import annotations

from homeassistant.const import CONF_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OverwatchAPI
from .coordinator import OverwatchConfigEntry, OverwatchCoordinator
from .panel import async_register_module, async_remove_panel, async_sync_panel

PLATFORMS = [Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: OverwatchConfigEntry) -> bool:
    api = OverwatchAPI(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
    coordinator = OverwatchCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_changed))
    # The sidebar panel follows what Overwatch says on each refresh: it's there
    # while Overwatch allows this Home Assistant to frame it.
    await async_register_module(hass)
    async_sync_panel(hass, entry, coordinator)
    entry.async_on_unload(coordinator.async_add_listener(lambda: async_sync_panel(hass, entry, coordinator)))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OverwatchConfigEntry) -> bool:
    async_remove_panel(hass, entry)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _options_changed(hass: HomeAssistant, entry: OverwatchConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
