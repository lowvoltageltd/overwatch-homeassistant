"""Each Overwatch camera as a camera entity.

Live video is WebRTC straight from Overwatch's go2rtc: the integration hands the
Home Assistant app's offer to Overwatch, so the video takes Overwatch's route,
which works away from home when Overwatch has a WebRTC port forward (Home
Assistant's own route falls back to HLS there, which was choppy). Older Overwatch
versions: go2rtc's RTSP restream on the LAN, played by Home Assistant's go2rtc.
Stills are Overwatch's snapshots. Each camera links to its page in Overwatch
(the device's Visit link, and the `url` attribute for a card's tap action), at
the address Overwatch gives for links (Remote access), else the one it was
added with.
Cameras added in Overwatch appear on the next refresh; removed ones go away.
"""

from __future__ import annotations

from homeassistant.components.camera import Camera, CameraEntityFeature, WebRTCAnswer, WebRTCError, WebRTCSendMessage
from webrtc_models import RTCIceCandidateInit
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import OverwatchCamera, OverwatchError
from .const import CONF_STREAM, DOMAIN, STREAM_SUB
from .coordinator import OverwatchConfigEntry, OverwatchCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OverwatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def sync() -> None:
        current = set(coordinator.data.cameras)
        if new := current - known:
            known.update(new)
            async_add_entities(OverwatchCameraEntity(coordinator, cam_id) for cam_id in sorted(new))
        if gone := known - current:
            known.difference_update(gone)
            _remove(hass, entry, gone)

    sync()
    entry.async_on_unload(coordinator.async_add_listener(sync))


def _remove(hass: HomeAssistant, entry: OverwatchConfigEntry, ids: set[str]) -> None:
    """Drop the entities and devices of cameras deleted in Overwatch."""
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
    for cam_id in ids:
        uid = _unique_id(entry, cam_id)
        if entity_id := ent_reg.async_get_entity_id("camera", DOMAIN, uid):
            ent_reg.async_remove(entity_id)
        if device := _device(dev_reg, entry, uid):
            dev_reg.async_remove_device(device.id)


def _device(dev_reg: dr.DeviceRegistry, entry: OverwatchConfigEntry, uid: str) -> dr.DeviceEntry | None:
    # Home Assistant 2026.10 scopes devices to their config entry; older versions
    # look them up by identifier alone.
    if hasattr(dev_reg, "async_get_device_by_identifier"):
        return dev_reg.async_get_device_by_identifier((DOMAIN, uid), entry.entry_id)
    return dev_reg.async_get_device(identifiers={(DOMAIN, uid)})


def _unique_id(entry: OverwatchConfigEntry, cam_id: str) -> str:
    return f"{entry.unique_id}/{cam_id}"


class OverwatchCameraEntity(CoordinatorEntity[OverwatchCoordinator], Camera):
    _attr_has_entity_name = True
    _attr_name = None  # the camera is the device: camera.door_bell

    def __init__(self, coordinator: OverwatchCoordinator, cam_id: str) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._cam_id = cam_id
        # Home Assistant decides "native WebRTC" from the method being overridden;
        # against an Overwatch that can't answer offers, keep its restream path.
        self._supports_native_async_webrtc = coordinator.data.webrtc
        entry = coordinator.config_entry
        self._attr_unique_id = _unique_id(entry, cam_id)
        cam = self._camera
        self._attr_device_info = DeviceInfo(
            # Its own device: Home Assistant keeps a device to one integration, so
            # it can't join the one MQTT discovery made for the detection sensors.
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=cam.name if cam else cam_id,
            manufacturer=cam.manufacturer if cam else None,
            model=cam.model if cam else None,
            configuration_url=self._page(),
        )

    def _page(self) -> str:
        return self.coordinator.api.camera_page(self._cam_id, self.coordinator.data.url)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"url": self._page()}

    @property
    def _camera(self) -> OverwatchCamera | None:
        return self.coordinator.data.cameras.get(self._cam_id)

    @property
    def available(self) -> bool:
        return super().available and self._camera is not None

    @property
    def supported_features(self) -> CameraEntityFeature:
        # Live video is WebRTC from Overwatch, or the restream on the LAN; with
        # neither, stills only.
        data = self.coordinator.data
        return CameraEntityFeature.STREAM if data.webrtc or data.rtsp else CameraEntityFeature(0)

    def _sub(self) -> bool:
        cam = self._camera
        return self.coordinator.config_entry.options.get(CONF_STREAM) == STREAM_SUB and cam is not None and cam.sub is not None

    async def async_handle_async_webrtc_offer(self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage) -> None:
        try:
            answer = await self.coordinator.api.webrtc_offer(self._cam_id, offer_sdp, self._sub())
        except OverwatchError as err:
            send_message(WebRTCError("webrtc_offer_failed", f"Overwatch: {err}"))
            return
        send_message(WebRTCAnswer(answer))

    async def async_on_webrtc_candidate(self, session_id: str, candidate: RTCIceCandidateInit) -> None:
        # go2rtc's answer already carries its candidates, and it learns the app's
        # address from the app's connectivity checks: nothing to pass on.
        return

    async def stream_source(self) -> str | None:
        cam, rtsp = self._camera, self.coordinator.data.rtsp
        if cam is None or rtsp is None:
            return None
        path = cam.main
        if self.coordinator.config_entry.options.get(CONF_STREAM) == STREAM_SUB and cam.sub:
            path = cam.sub
        return self.coordinator.api.stream_url(rtsp, path)

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        try:
            return await self.coordinator.api.snapshot(self._cam_id, width)
        except OverwatchError as err:
            raise HomeAssistantError(f"Overwatch snapshot failed: {err}") from err

    @callback
    def _handle_coordinator_update(self) -> None:
        # A camera renamed in Overwatch keeps its entity id; its device name follows.
        # So does the Visit link when the address for links changes.
        if (cam := self._camera) and self.device_entry:
            changes = {}
            if self.device_entry.name != cam.name:
                changes["name"] = cam.name
            if self.device_entry.configuration_url != (page := self._page()):
                changes["configuration_url"] = page
            if changes:
                dr.async_get(self.hass).async_update_device(self.device_entry.id, **changes)
        super()._handle_coordinator_update()
