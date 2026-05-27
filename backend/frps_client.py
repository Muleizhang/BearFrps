from __future__ import annotations

from typing import Any

import httpx

from backend.config import Settings


class FrpsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list_tcp_proxies(self) -> list[dict[str, Any]]:
        data = await self._get_json("/api/proxy/tcp")
        proxies = data.get("proxies", [])
        return proxies if isinstance(proxies, list) else []

    async def get_proxy_traffic(self, name: str) -> dict[str, Any]:
        return await self._get_json(f"/api/traffic/{name}")

    async def clear_offline_proxies(self) -> None:
        try:
            await self._request("DELETE", "/api/proxies", params={"status": "offline"})
        except httpx.HTTPError:
            return

    async def kick_proxy(self, name: str) -> None:
        # frps v0.58.1 has no single-proxy kick endpoint. Keep this method so callers
        # can express intent while stop enforcement happens through plugin rejects.
        return None

    async def _get_json(self, path: str) -> dict[str, Any]:
        response = await self._request("GET", path)
        return response.json()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = self.settings.frps_admin_api_url.rstrip("/") + path
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.request(
                method,
                url,
                auth=(self.settings.frps_admin_user, self.settings.frps_admin_password),
                **kwargs,
            )
        response.raise_for_status()
        return response
