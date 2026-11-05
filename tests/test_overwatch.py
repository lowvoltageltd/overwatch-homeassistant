"""The Overwatch integration against a fake Overwatch API."""

from datetime import timedelta

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.camera import CameraEntityFeature, async_get_image, async_get_stream_source
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.overwatch.const import CONF_STREAM, DOMAIN

URL = "http://192.168.1.10:8080"
TOKEN = "owt_test"
RTSP = {"port": 8554, "username": "overwatch", "password": "p@ss/word"}
DOORBELL = {"id": "door-bell", "name": "Door Bell", "manufacturer": "Reolink", "model": "Video Doorbell WiFi", "main": "door-bell", "sub": "door-bell_sub"}
STREET = {"id": "the-street", "name": "The Street", "main": "the-street"}


def answer(aioclient_mock: AiohttpClientMocker, cameras, rtsp=RTSP, status=200, url=None, embed=None):
    aioclient_mock.clear_requests()
    body = {"rtsp": rtsp, "cameras": cameras}
    if url is not None:
        body["url"] = url
    if embed is not None:
        body["embed"] = embed
    aioclient_mock.get(f"{URL}/api/homeassistant/cameras", status=status, json=body)


async def setup(hass: HomeAssistant, options=None) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=URL, data={CONF_URL: URL, CONF_TOKEN: TOKEN}, options=options or {})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    answer(aioclient_mock, [DOORBELL])
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: "192.168.1.10:8080/", CONF_TOKEN: f" {TOKEN} "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_URL: URL, CONF_TOKEN: TOKEN}
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == f"Bearer {TOKEN}"


async def test_config_flow_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    answer(aioclient_mock, [], status=401)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_TOKEN: "owt_wrong"})
    assert result["errors"] == {"base": "invalid_auth"}
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/homeassistant/cameras", exc=TimeoutError)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_TOKEN: TOKEN})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_cameras(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    answer(aioclient_mock, [DOORBELL, STREET])
    await setup(hass)

    state = hass.states.get("camera.door_bell")
    assert state is not None, hass.states.async_entity_ids("camera")
    assert state.attributes["supported_features"] & CameraEntityFeature.STREAM
    # The login is URL-encoded into the restream address, on Overwatch's host.
    assert await async_get_stream_source(hass, "camera.door_bell") == "rtsp://overwatch:p%40ss%2Fword@192.168.1.10:8554/door-bell"

    entity = er.async_get(hass).async_get("camera.door_bell")
    device = dr.async_get(hass).async_get(entity.device_id)
    assert device.name == "Door Bell" and device.manufacturer == "Reolink" and device.configuration_url == f"{URL}/cameras/door-bell"

    aioclient_mock.get(f"{URL}/api/cameras/door-bell/snapshot", content=b"jpeg!")
    image = await async_get_image(hass, "camera.door_bell", width=640)
    assert image.content == b"jpeg!"
    assert str(aioclient_mock.mock_calls[-1][1]).endswith("snapshot?width=640")


async def test_links_use_overwatchs_address(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    answer(aioclient_mock, [DOORBELL], url="https://nvr.example.com/")
    await setup(hass)
    assert hass.states.get("camera.door_bell").attributes["url"] == "https://nvr.example.com/cameras/door-bell"
    entity = er.async_get(hass).async_get("camera.door_bell")
    assert dr.async_get(hass).async_get(entity.device_id).configuration_url == "https://nvr.example.com/cameras/door-bell"

    # Changed in Overwatch: the Visit link follows on the next refresh.
    answer(aioclient_mock, [DOORBELL], url="https://other.example.com")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert dr.async_get(hass).async_get(entity.device_id).configuration_url == "https://other.example.com/cameras/door-bell"
    assert hass.states.get("camera.door_bell").attributes["url"] == "https://other.example.com/cameras/door-bell"


async def test_sub_stream_option(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    answer(aioclient_mock, [DOORBELL, STREET])
    await setup(hass, options={CONF_STREAM: "sub"})
    assert (await async_get_stream_source(hass, "camera.door_bell")).endswith("/door-bell_sub")
    # A camera without a sub stream plays its main one.
    assert (await async_get_stream_source(hass, "camera.the_street")).endswith("/the-street")


async def test_no_lan_restream(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    answer(aioclient_mock, [DOORBELL], rtsp=None)
    await setup(hass)
    state = hass.states.get("camera.door_bell")
    assert not state.attributes["supported_features"] & CameraEntityFeature.STREAM


async def test_cameras_follow_overwatch(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    answer(aioclient_mock, [DOORBELL])
    await setup(hass)
    assert hass.states.async_entity_ids("camera") == ["camera.door_bell"]

    # Added and renamed in Overwatch, then picked up on the next refresh.
    answer(aioclient_mock, [{**DOORBELL, "name": "Front Door"}, STREET])
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert sorted(hass.states.async_entity_ids("camera")) == ["camera.door_bell", "camera.the_street"]
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get("camera.door_bell").device_id)
    assert device.name == "Front Door"

    # Deleted in Overwatch: its entity and device go.
    device_id = device.id
    answer(aioclient_mock, [STREET])
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=122))
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get_entity_id("camera", DOMAIN, f"{URL}/door-bell") is None
    assert dr.async_get(hass).async_get(device_id) is None


async def test_revoked_token_asks_again(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    answer(aioclient_mock, [DOORBELL])
    entry = await setup(hass)
    answer(aioclient_mock, [], status=401)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" and f["context"]["entry_id"] == entry.entry_id for f in flows)


async def test_webrtc_from_overwatch(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_ws_client) -> None:
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/homeassistant/cameras", json={"rtsp": RTSP, "cameras": [DOORBELL], "webrtc": True})
    aioclient_mock.post(f"{URL}/api/cameras/door-bell/webrtc", text="v=0\r\nanswer")
    await setup(hass, options={CONF_STREAM: "sub"})
    ws = await hass_ws_client(hass)

    # Native WebRTC only: no HLS fallback (that was the choppy path on 4G).
    await ws.send_json({"id": 1, "type": "camera/capabilities", "entity_id": "camera.door_bell"})
    msg = await ws.receive_json()
    assert msg["result"]["frontend_stream_types"] == ["web_rtc"]

    await ws.send_json({"id": 2, "type": "camera/webrtc/offer", "entity_id": "camera.door_bell", "offer": "v=0\r\noffer"})
    assert (await ws.receive_json())["success"]
    assert (await ws.receive_json())["event"]["type"] == "session"
    msg = await ws.receive_json()
    assert msg["event"] == {"type": "answer", "answer": "v=0\r\nanswer"}
    call = aioclient_mock.mock_calls[-1]
    assert call[2] == "v=0\r\noffer" and str(call[1]).endswith("webrtc?stream=sub")
    assert call[3]["Authorization"] == f"Bearer {TOKEN}"


async def test_webrtc_older_overwatch(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, hass_ws_client) -> None:
    answer(aioclient_mock, [DOORBELL])  # no "webrtc": Home Assistant plays the restream
    await setup(hass)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "camera/capabilities", "entity_id": "camera.door_bell"})
    msg = await ws.receive_json()
    assert "hls" in msg["result"]["frontend_stream_types"]


async def test_sidebar_panel_follows_overwatch(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    # Overwatch doesn't allow framing (or is older): no panel to show a refusal.
    answer(aioclient_mock, [DOORBELL])
    entry = await setup(hass)
    assert "overwatch" not in hass.data.get(DATA_PANELS, {})

    # Allowed: the panel opens the address links use, not the LAN one.
    answer(aioclient_mock, [DOORBELL], url="https://nvr.example.com/", embed=True)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    panel = hass.data[DATA_PANELS]["overwatch"]
    assert panel.component_name == "custom" and panel.sidebar_title == "Overwatch"
    assert panel.config["url"] == "https://nvr.example.com" and panel.config["_panel_custom"]["module_url"].startswith("/overwatch_panel/overwatch-panel.js?v=")
    assert not panel.require_admin

    # Withdrawn in Overwatch's Settings: the item goes on the next refresh.
    answer(aioclient_mock, [DOORBELL], url="https://nvr.example.com/", embed=False)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=122))
    await hass.async_block_till_done()
    assert "overwatch" not in hass.data[DATA_PANELS]

    # Allowed again, without an address for links: the one Home Assistant uses.
    answer(aioclient_mock, [DOORBELL], embed=True)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=183))
    await hass.async_block_till_done()
    assert hass.data[DATA_PANELS]["overwatch"].config["url"] == URL

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert "overwatch" not in hass.data[DATA_PANELS]
