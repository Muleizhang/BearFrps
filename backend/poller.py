from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from backend.frps_client import FrpsClient
from backend.models import Proxy, ProxyStatus, store


class UsagePoller:
    def __init__(self, frps_client: FrpsClient, interval_sec: int) -> None:
        self.frps_client = frps_client
        self.interval_sec = max(1, interval_sec)
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_event = asyncio.Event()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._stop_event = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), self.interval_sec)
            except TimeoutError:
                continue

    async def poll_once(self) -> None:
        try:
            proxy_infos = await self.frps_client.list_tcp_proxies()
        except Exception:
            return
        by_name = {
            str(info.get("name")): info
            for info in proxy_infos
            if info.get("name") is not None
        }
        async with store.lock:
            for proxy in store.proxies.values():
                if proxy.status == ProxyStatus.DELETED:
                    continue
                info = by_name.get(proxy.frps_name)
                _apply_poll_info(proxy, info, self.interval_sec)
                _apply_stop_rules(proxy)


def _apply_poll_info(proxy: Proxy, info: dict[str, Any] | None, interval_sec: int) -> None:
    if not info:
        proxy.is_online = False
        proxy.current_speed_bps = 0
        proxy.last_frps_total_bytes = None
        return

    frps_status = str(info.get("status", ""))
    proxy.is_online = frps_status == "online"
    if proxy.is_online:
        proxy.last_seen_at = datetime.now(UTC)

    conf = info.get("conf") if isinstance(info.get("conf"), dict) else {}
    local_port = conf.get("localPort")
    if isinstance(local_port, int):
        proxy.actual_local_port = local_port

    total_bytes = _as_int(info.get("todayTrafficIn")) + _as_int(info.get("todayTrafficOut"))
    if proxy.last_frps_total_bytes is None or total_bytes < proxy.last_frps_total_bytes:
        delta = 0
    else:
        delta = total_bytes - proxy.last_frps_total_bytes
    proxy.last_frps_total_bytes = total_bytes

    if delta > 0:
        proxy.traffic_used_bytes += delta
        user = store.users.get(proxy.uid)
        if user:
            used_mb = delta // (1024 * 1024)
            if delta % (1024 * 1024):
                used_mb += 1
            user.balance_mb = max(0, user.balance_mb - used_mb)

    proxy.current_speed_bps = int(delta / max(1, interval_sec))


def _apply_stop_rules(proxy: Proxy) -> None:
    if proxy.status != ProxyStatus.ACTIVE:
        return
    user = store.users.get(proxy.uid)
    if user and user.balance_mb <= 0:
        proxy.status = ProxyStatus.STOPPED_BY_ADMIN
        proxy.is_online = False
        return
    if proxy.traffic_used_bytes >= proxy.traffic_limit_mb * 1024 * 1024:
        proxy.status = ProxyStatus.STOPPED_BY_ADMIN
        proxy.is_online = False


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
