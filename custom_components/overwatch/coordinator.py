"""Keeps Overwatch's camera list (and the restream login) up to date."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import Cameras, OverwatchAPI, OverwatchAuthError, OverwatchError
from .const import DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

type OverwatchConfigEntry = ConfigEntry[OverwatchCoordinator]


class OverwatchCoordinator(DataUpdateCoordinator[Cameras]):
    config_entry: OverwatchConfigEntry

    def __init__(self, hass: HomeAssistant, entry: OverwatchConfigEntry, api: OverwatchAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api

    async def _async_update_data(self) -> Cameras:
        try:
            return await self.api.cameras()
        except OverwatchAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OverwatchError as err:
            raise UpdateFailed(str(err)) from err
