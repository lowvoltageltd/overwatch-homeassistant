"""Overwatch in Home Assistant's sidebar: its web app in a panel of its own.

The panel (www/overwatch-panel.js) is an iframe that follows the address:
/overwatch/cameras/driveway in Home Assistant opens that page in Overwatch,
and moving around in Overwatch updates Home Assistant's address bar.

Overwatch refuses to be framed unless Settings → Remote access names this Home
Assistant's address, and says so in its camera list (`embed`); until then there
is no panel to show a "refused to connect" page in.
"""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .coordinator import OverwatchConfigEntry, OverwatchCoordinator

PANEL = "overwatch"
MODULE_URL = "/overwatch_panel/overwatch-panel.js"
MODULE_PATH = Path(__file__).parent / "www" / "overwatch-panel.js"
# The browser keeps a panel's script until its address changes: the version
# in the query makes an update take effect without a hard refresh.
VERSION = json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]


async def async_register_module(hass: HomeAssistant) -> None:
    """Serve the panel's script, once."""
    if hass.data.get(f"{PANEL}_module"):
        return
    await hass.http.async_register_static_paths([StaticPathConfig(MODULE_URL, str(MODULE_PATH), False)])
    hass.data[f"{PANEL}_module"] = True


def async_sync_panel(hass: HomeAssistant, entry: OverwatchConfigEntry, coordinator: OverwatchCoordinator) -> None:
    """Add, repoint or remove the panel to match what Overwatch allows now."""
    cameras = coordinator.data
    if cameras is None or not cameras.embed:
        async_remove_panel(hass, entry)
        return
    # The address the browser opens, which may differ from the one Home
    # Assistant itself uses (the LAN address): Overwatch's address for links first.
    url = cameras.url or coordinator.api.url
    panels = hass.data.get(frontend.DATA_PANELS, {})
    config = {"url": url, "_panel_custom": {"name": "overwatch-panel", "embed_iframe": False, "trust_external": False, "module_url": f"{MODULE_URL}?v={VERSION}"}}
    if (existing := panels.get(PANEL)) is not None and existing.config == config:
        return
    frontend.async_register_built_in_panel(
        hass,
        "custom",
        sidebar_title="Overwatch",
        sidebar_icon="mdi:cctv",
        frontend_url_path=PANEL,
        config=config,
        require_admin=False,
        update=True,
    )


def async_remove_panel(hass: HomeAssistant, entry: OverwatchConfigEntry) -> None:
    if PANEL in hass.data.get(frontend.DATA_PANELS, {}):
        frontend.async_remove_panel(hass, PANEL)
