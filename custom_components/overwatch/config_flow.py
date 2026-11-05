"""Set up Overwatch: its address and an API token made in Overwatch's settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig, SelectSelectorMode

from .api import OverwatchAPI, OverwatchAuthError, OverwatchError
from .const import CONF_STREAM, DOMAIN, STREAM_MAIN, STREAM_SUB


def _normalise(url: str) -> str:
    url = url.strip().rstrip("/")
    if "://" not in url:
        url = "http://" + url
    return url


class OverwatchConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, url: str, token: str) -> str | None:
        """The error key for these details, or None if they work."""
        try:
            await OverwatchAPI(async_get_clientsession(self.hass), url, token).cameras()
        except OverwatchAuthError:
            return "invalid_auth"
        except OverwatchError:
            return "cannot_connect"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalise(user_input[CONF_URL])
            token = user_input[CONF_TOKEN].strip()
            if not urlsplit(url).hostname:
                errors[CONF_URL] = "invalid_url"
            elif (error := await self._check(url, token)) is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(url.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=urlsplit(url).hostname or url,
                    data={CONF_URL: url, CONF_TOKEN: token},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_URL): str, vol.Required(CONF_TOKEN): str}),
                user_input or {},
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """A revoked token: ask for a new one."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if (error := await self._check(entry.data[CONF_URL], token)) is not None:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OverwatchOptionsFlow()


class OverwatchOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_STREAM, default=self.config_entry.options.get(CONF_STREAM, STREAM_MAIN)
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[STREAM_MAIN, STREAM_SUB],
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_STREAM,
                        )
                    ),
                }
            ),
        )
