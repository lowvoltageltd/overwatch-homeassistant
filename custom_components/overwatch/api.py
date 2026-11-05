"""Overwatch's HTTP API, as far as Home Assistant needs it.

Overwatch hands an API token exactly three things: the camera list (with the
login for its go2rtc RTSP restream on the LAN), each camera's snapshot, and
WebRTC live view (it answers the Home Assistant app's offer).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import aiohttp


class OverwatchError(Exception):
    """Overwatch couldn't be reached, or answered with an error."""


class OverwatchAuthError(OverwatchError):
    """The token was refused."""


@dataclass(frozen=True)
class RTSP:
    port: int
    username: str
    password: str


@dataclass(frozen=True)
class OverwatchCamera:
    id: str
    name: str
    manufacturer: str | None
    model: str | None
    main: str
    sub: str | None


@dataclass(frozen=True)
class Cameras:
    rtsp: RTSP | None  # None: the restream isn't reachable from the LAN
    cameras: dict[str, OverwatchCamera]
    webrtc: bool = False  # Overwatch answers WebRTC offers (0.13 and later)
    url: str | None = None  # where links into the web app point from anywhere (0.15 and later)
    embed: bool = False  # Overwatch lets this Home Assistant frame it (0.18 and later)


class OverwatchAPI:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self.url = url.rstrip("/")
        self._token = token

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""

    async def _get(self, path: str, params: dict | None = None) -> aiohttp.ClientResponse:
        return await self._request("GET", path, params)

    async def _request(self, method: str, path: str, params: dict | None = None, data: str | None = None) -> aiohttp.ClientResponse:
        headers = {"Authorization": f"Bearer {self._token}"}
        if data is not None:
            headers["Content-Type"] = "application/sdp"
        try:
            res = await self._session.request(
                method,
                self.url + path,
                params=params,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise OverwatchError(f"can't reach Overwatch: {err}") from err
        if res.status in (401, 403):
            res.release()
            raise OverwatchAuthError("Overwatch refused the token")
        if res.status != 200:
            res.release()
            raise OverwatchError(f"Overwatch answered HTTP {res.status}")
        return res

    async def cameras(self) -> Cameras:
        res = await self._get("/api/homeassistant/cameras")
        data = await res.json()
        rtsp = data.get("rtsp")
        return Cameras(
            rtsp=RTSP(rtsp["port"], rtsp["username"], rtsp["password"]) if rtsp else None,
            cameras={
                c["id"]: OverwatchCamera(
                    id=c["id"],
                    name=c["name"],
                    manufacturer=c.get("manufacturer") or None,
                    model=c.get("model") or None,
                    main=c["main"],
                    sub=c.get("sub") or None,
                )
                for c in data.get("cameras", [])
            },
            webrtc=bool(data.get("webrtc")),
            url=(data.get("url") or "").rstrip("/") or None,
            embed=bool(data.get("embed")),
        )

    async def snapshot(self, camera_id: str, width: int | None = None) -> bytes:
        params = {"width": str(width)} if width else None
        res = await self._get(f"/api/cameras/{quote(camera_id, safe='')}/snapshot", params)
        return await res.read()

    async def webrtc_offer(self, camera_id: str, offer: str, sub: bool = False) -> str:
        """Overwatch's go2rtc answers the app's SDP offer (its candidates included)."""
        params = {"stream": "sub"} if sub else None
        res = await self._request("POST", f"/api/cameras/{quote(camera_id, safe='')}/webrtc", params, offer)
        return await res.text()

    def camera_page(self, camera_id: str, base: str | None) -> str:
        """The camera's page in the web app (live view and its timeline)."""
        return f"{base or self.url}/cameras/{quote(camera_id, safe='')}"

    def stream_url(self, rtsp: RTSP, path: str) -> str:
        """The restream URL for a go2rtc stream, with the login in it."""
        login = f"{quote(rtsp.username, safe='')}:{quote(rtsp.password, safe='')}@"
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"rtsp://{login}{host}:{rtsp.port}/{quote(path, safe='')}"
