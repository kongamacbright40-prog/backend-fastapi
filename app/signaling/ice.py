"""ICE servers (STUN + TURN) handed to the app for live-class audio/video.

STUN only helps two devices discover a direct path. When that path is blocked
(mobile data, campus/office networks, most routers on different networks)
audio and video only flow through a TURN relay. The relay is configured on the
server (see config.py) so it can be changed without rebuilding the app, and
provider secrets never ship inside the app.
"""

import json
import logging
import threading
import time
import urllib.request

from app.config import settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: tuple[float, list[dict]] | None = None  # (expires_at, turn servers)

# Provider credentials are fetched at most this often (they are valid longer).
_CACHE_SECONDS = 6 * 3600
_RETRY_AFTER_FAILURE_SECONDS = 60
_CLOUDFLARE_TTL_SECONDS = 24 * 3600


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def _is_turn(server: dict) -> bool:
    urls = server.get("urls") or server.get("url") or []
    if isinstance(urls, str):
        urls = [urls]
    return any(str(u).startswith(("turn:", "turns:")) for u in urls)


def _fetch_provider_servers() -> list[dict]:
    """TURN servers from Metered or Cloudflare (raises on network errors)."""
    if settings.metered_domain and settings.metered_api_key:
        domain = settings.metered_domain.removeprefix("https://").strip("/")
        servers = _http_json(f"https://{domain}/api/v1/turn/credentials?apiKey={settings.metered_api_key}")
        return [s for s in servers if _is_turn(s)]
    if settings.cloudflare_turn_key_id and settings.cloudflare_turn_api_token:
        result = _http_json(
            f"https://rtc.live.cloudflare.com/v1/turn/keys/{settings.cloudflare_turn_key_id}"
            "/credentials/generate-ice-servers",
            method="POST",
            body={"ttl": _CLOUDFLARE_TTL_SECONDS},
            headers={"Authorization": f"Bearer {settings.cloudflare_turn_api_token}"},
        )
        servers = result.get("iceServers", [])
        if isinstance(servers, dict):
            servers = [servers]
        return [s for s in servers if _is_turn(s)]
    return []


def _provider_servers() -> list[dict]:
    global _cache
    if not ((settings.metered_domain and settings.metered_api_key)
            or (settings.cloudflare_turn_key_id and settings.cloudflare_turn_api_token)):
        return []
    with _lock:
        now = time.monotonic()
        if _cache is not None and _cache[0] > now:
            return _cache[1]
        try:
            servers = _fetch_provider_servers()
            _cache = (now + _CACHE_SECONDS, servers)
            if not servers:
                log.warning("The TURN provider returned no TURN servers; check its credentials.")
        except Exception as exc:  # network / auth problems must not break classes
            log.warning("Could not fetch TURN credentials from the provider: %s", exc)
            servers = _cache[1] if _cache else []
            _cache = (now + _RETRY_AFTER_FAILURE_SECONDS, servers)
        return servers


def turn_configured() -> bool:
    return bool(_split(settings.turn_urls)) or bool(
        (settings.metered_domain and settings.metered_api_key)
        or (settings.cloudflare_turn_key_id and settings.cloudflare_turn_api_token)
    )


def ice_servers() -> list[dict]:
    servers: list[dict] = []
    stun = _split(settings.stun_urls)
    if stun:
        servers.append({"urls": stun})
    turn = _split(settings.turn_urls)
    if turn:
        servers.append({
            "urls": turn,
            "username": settings.turn_username,
            "credential": settings.turn_credential,
        })
    servers.extend(_provider_servers())
    return servers


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None
