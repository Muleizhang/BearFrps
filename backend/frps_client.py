"""@file backend/frps_client.py
@brief 封装 frps admin API 查询和清理接口，供轮询器读取在线代理状态。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：httpx、backend.config.Settings。
  修改记录：2026-06-10，补充 Doxygen 风格文件头、接口说明和 frps 兼容说明。
  list_tcp_proxies/list_http_proxies/list_stcp_proxies/list_xtcp_proxies：
    查询 frps 当前代理列表，返回原始 JSON 中的 proxies 数组。
  get_proxy_traffic：查询单个代理的详细流量信息。
  clear_offline_proxies：调用 frps 清理离线代理，减少展示页脏状态。
  kick_proxy：保留停用意图接口，实际停用主要依赖插件拒绝后续连接。

  frps v0.58.1 没有稳定的单代理踢下线接口，所以 kick_proxy 不直接删除进程内连接。
  轮询器和插件共同保证超额或停用代理不能继续建立新会话。
"""

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

    async def list_http_proxies(self) -> list[dict[str, Any]]:
        data = await self._get_json("/api/proxy/http")
        proxies = data.get("proxies", [])
        return proxies if isinstance(proxies, list) else []

    async def list_stcp_proxies(self) -> list[dict[str, Any]]:
        data = await self._get_json("/api/proxy/stcp")
        proxies = data.get("proxies", [])
        return proxies if isinstance(proxies, list) else []

    async def list_xtcp_proxies(self) -> list[dict[str, Any]]:
        data = await self._get_json("/api/proxy/xtcp")
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
