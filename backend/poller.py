from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from backend.frps_client import FrpsClient
from backend.models import Proxy, ProxyStatus, ProxyType, TcpMapping, store
from backend.user_persistence import save_registered_users_unlocked


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
        proxy_infos = await self._list_all_proxy_infos()
        if proxy_infos is None:
            return
        by_name = {
            str(info.get("name")): info
            for info in proxy_infos
            if info.get("name") is not None
        }
        async with store.lock:
            users_changed = False
            for proxy in store.proxies.values():
                if proxy.status == ProxyStatus.DELETED:
                    continue
                if proxy.proxy_type == ProxyType.TCP:
                    users_changed = (
                        _apply_tcp_poll_info(proxy, by_name, self.interval_sec) or users_changed
                    )
                elif proxy.proxy_type == ProxyType.HTTP:
                    info = by_name.get(proxy.frps_name)
                    users_changed = _apply_poll_info(proxy, info, self.interval_sec) or users_changed
                else:
                    users_changed = (
                        _apply_p2p_poll_info(proxy, by_name, self.interval_sec) or users_changed
                    )
                _apply_stop_rules(proxy)
            if users_changed:
                save_registered_users_unlocked(store)

    async def _list_all_proxy_infos(self) -> list[dict[str, Any]] | None:
        try:
            proxy_infos = await self.frps_client.list_tcp_proxies()
        except Exception:
            return None
        for method_name in (
            "list_http_proxies",
            "list_stcp_proxies",
            "list_xtcp_proxies",
        ):
            method = getattr(self.frps_client, method_name, None)
            if method is None:
                continue
            try:
                proxy_infos = proxy_infos + await method()
            except Exception:
                continue
        return proxy_infos


def _apply_tcp_poll_info(
    proxy: Proxy, by_name: dict[str, dict[str, Any]], interval_sec: int
) -> bool:
    total_delta = 0
    for mapping in proxy.tcp_mappings:
        info = by_name.get(mapping.frps_name)
        total_delta += _apply_tcp_mapping_poll_info(proxy, mapping, info, interval_sec)

    proxy.is_online = any(mapping.is_online for mapping in proxy.tcp_mappings)
    if proxy.is_online:
        proxy.last_seen_at = datetime.now(UTC)
    proxy.current_speed_bps = sum(mapping.current_speed_bps for mapping in proxy.tcp_mappings)
    if proxy.tcp_mappings:
        first = proxy.tcp_mappings[0]
        proxy.frps_remote_port = first.remote_port
        proxy.local_port = first.local_port
        proxy.actual_local_port = first.actual_local_port
        proxy.last_frps_total_bytes = first.last_frps_total_bytes
    if total_delta > 0:
        return _charge_usage(proxy, total_delta)
    return False


def _apply_tcp_mapping_poll_info(
    proxy: Proxy,
    mapping: TcpMapping,
    info: dict[str, Any] | None,
    interval_sec: int,
) -> int:
    if not info:
        mapping.is_online = False
        mapping.current_speed_bps = 0
        mapping.last_frps_total_bytes = None
        return 0

    frps_status = str(info.get("status", ""))
    mapping.is_online = frps_status == "online"

    conf = info.get("conf") if isinstance(info.get("conf"), dict) else {}
    local_port = conf.get("localPort")
    if isinstance(local_port, int):
        mapping.actual_local_port = local_port

    if (
        len(proxy.tcp_mappings) == 1
        and mapping.last_frps_total_bytes is None
        and proxy.last_frps_total_bytes is not None
    ):
        mapping.last_frps_total_bytes = proxy.last_frps_total_bytes

    total_bytes = _as_int(info.get("todayTrafficIn")) + _as_int(info.get("todayTrafficOut"))
    if mapping.last_frps_total_bytes is None or total_bytes < mapping.last_frps_total_bytes:
        delta = 0
    else:
        delta = total_bytes - mapping.last_frps_total_bytes
    mapping.last_frps_total_bytes = total_bytes
    mapping.current_speed_bps = int(delta / max(1, interval_sec))
    return delta


def _apply_poll_info(proxy: Proxy, info: dict[str, Any] | None, interval_sec: int) -> bool:
    if not info:
        proxy.is_online = False
        proxy.current_speed_bps = 0
        proxy.last_frps_total_bytes = None
        return False

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

    proxy.current_speed_bps = int(delta / max(1, interval_sec))
    if delta > 0:
        return _charge_usage(proxy, delta)
    return False


def _apply_p2p_poll_info(
    proxy: Proxy, by_name: dict[str, dict[str, Any]], interval_sec: int
) -> bool:
    xtcp_info = by_name.get(proxy.frps_name)
    fallback_info = by_name.get(proxy.p2p_fallback_name or "")
    proxy.p2p_xtcp_is_online = _is_online(xtcp_info)
    proxy.p2p_fallback_is_online = _is_online(fallback_info)
    proxy.is_online = proxy.p2p_xtcp_is_online or proxy.p2p_fallback_is_online
    if proxy.is_online:
        proxy.last_seen_at = datetime.now(UTC)

    if fallback_info:
        changed = _apply_poll_info(proxy, fallback_info, interval_sec)
        proxy.is_online = proxy.p2p_xtcp_is_online or proxy.p2p_fallback_is_online
        return changed

    proxy.current_speed_bps = 0
    proxy.last_frps_total_bytes = None
    return False


def _charge_usage(proxy: Proxy, delta: int) -> bool:
    proxy.traffic_used_bytes += delta
    user = store.users.get(proxy.uid)
    if not user:
        return False
    used_mb = delta // (1024 * 1024)
    if delta % (1024 * 1024):
        used_mb += 1
    user.balance_mb = max(0, user.balance_mb - used_mb)
    return bool(user.username and user.password_hash)


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


def _is_online(info: dict[str, Any] | None) -> bool:
    if not info:
        return False
    return str(info.get("status", "")) == "online"
