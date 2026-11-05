# Overwatch NVR for Home Assistant

For people running an Overwatch NVR server (Low Voltage Limited). This integration
needs one; it does nothing on its own.

A custom integration that turns every Overwatch camera into a Home Assistant
camera entity, with live video in the standard cards (no custom card).

- **Live video** is WebRTC straight from Overwatch's go2rtc (Overwatch 0.13
  and later): the integration hands the Home Assistant app's request to
  Overwatch, so the video takes Overwatch's route. Away from home that's
  Overwatch's WebRTC port forward (Settings → Remote access), smooth on 4G,
  where Home Assistant's own route falls back to choppy HLS. Older Overwatch:
  Home Assistant's go2rtc plays Overwatch's RTSP restream on your network.
  H.265 cameras play only in browsers that decode H.265.
- **Snapshots** come from Overwatch.
- **Cameras follow Overwatch:** added, renamed and deleted cameras are picked up
  within a minute.
- **Options:** live video from the main stream (default) or the lighter sub stream.
- **Links into Overwatch:** each camera's page in Overwatch (live view and its
  timeline) is the device's **Visit** link and the camera's `url` attribute. It
  uses the address set in Overwatch's Settings → Remote access → Address for
  links, else the Cloudflare Tunnel's, else the one the integration was added
  with (home only). Signed out, the page asks you to sign in first.

- **Overwatch in the sidebar** (integration 0.4.0, Overwatch 0.18): the whole web
  app (live view, timeline, events, Talk) as an "Overwatch" item in Home
  Assistant's sidebar, so the HA app never opens another app or browser. It
  appears only once Overwatch allows it: Settings → Remote access → Show
  Overwatch inside Home Assistant, with the address you open Home Assistant at.
  Overwatch refuses every other site's frame. Both addresses must be https if
  Home Assistant is opened over https (browsers block an http frame in an https
  page), and they must share a site for the sign-in cookie to reach the frame
  (two hostnames under one domain, or one machine at different ports). The panel
  opens the address for links, else the one the integration was added with.
  Sign in once in the panel. Withdraw the address in Overwatch and the item
  goes within a minute. From integration 0.5.0 the address follows the page:
  `/overwatch/cameras/driveway` in Home Assistant opens that camera, and moving
  around in Overwatch (0.19) updates Home Assistant's address bar. The panel
  also lets the frame use the microphone, for Talk.

Detection sensors, doorbell presses and online status still come over MQTT
(Overwatch's Settings → Home Assistant). Home Assistant keeps each device to one
integration, so a camera's video and its MQTT sensors are two devices with the
same name.

## Install

1. On the Overwatch host, the RTSP restream needs a password (`OW_RTSP_PASSWORD`
   in `docker/.env`); `scripts/deploy.sh` generates one. Without it Home Assistant
   gets snapshots but no live video.
2. Install the integration, either with HACS or by hand, then restart Home Assistant:
   - **HACS:** HACS → ⋮ → Custom repositories → add
     `https://github.com/lowvoltageltd/overwatch-homeassistant` as type
     **Integration** → download **Overwatch NVR**. Updates then arrive through HACS.
   - **By hand:** copy `custom_components/overwatch` into Home Assistant's
     `config/custom_components/`.
3. In Overwatch, Settings → Home Assistant → Cameras in Home Assistant: create a
   token (shown once).
4. In Home Assistant, Settings → Devices & services → Add integration →
   Overwatch NVR: enter Overwatch's address (as you open it in a browser) and
   the token.

## Tap a card to open the camera in Overwatch

Home Assistant sets what a tap does in each card, so add it to the card's YAML
(Edit card → Show code editor), with the address from the camera's `url`
attribute (Developer tools → States, or the device's Visit link):

```yaml
type: picture-entity
entity: camera.the_street
camera_view: live
tap_action:
  action: url
  url_path: https://overwatch.example.com/cameras/the-street
```

The same `tap_action` works on picture-glance cards. On an iPhone the link
opens in Safari, not the Overwatch home-screen app (iOS doesn't hand links to
web apps), so sign in there once.

## Tests

```bash
uv venv -p 3.14 .venv && uv pip install --python .venv/bin/python pytest-homeassistant-custom-component PyTurboJPEG
.venv/bin/python -m pytest
```

Run from this folder. They run against a fake Overwatch API.
