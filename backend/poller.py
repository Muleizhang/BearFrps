"""@file backend/poller.py
@brief 定时读取 frps admin API，更新代理在线状态、流量、速度和停用条件。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：asyncio、FrpsClient、Store、用户持久化模块。
  修改记录：2026-06-10，补充 Doxygen 风格文件头、计费逻辑和副作用说明。
  TCP 多端口代理按每个 frps_name 聚合流量，避免只统计首端口。
  HTTP、STCP、XTCP 使用不同 frps admin API 列表，按代理类型更新在线状态。
  当前速度由相邻两次累计流量差除以轮询间隔得到。
  超过代理流量上限或用户余额不足时，代理状态置为 stopped_by_admin。
  停用后不会立刻释放端口，释放由用户删除代理或管理员删除代理完成。

  单轮轮询失败不终止后台任务，下一轮继续尝试，适合 frps 短暂不可用场景。
  持久化用户失败不应影响内存状态更新，但测试会覆盖正常保存路径。
  start 创建后台任务，并为 stop_event 建立异步退出信号。
  stop 设置退出信号并等待任务结束，避免测试和应用关闭时遗留任务。
  _run 按 interval_sec 循环执行 _poll_once。
  _poll_once 依次读取 TCP、HTTP、STCP、XTCP 列表，再进入 store.lock 更新状态。
  更新时先处理在线代理，再把未出现在 frps 列表中的 active 代理标记离线。

  frps 返回的 todayTrafficIn/todayTrafficOut 是累计值。
  本平台把入站和出站相加作为代理总用量。
  当前速度用本轮累计值减去上一轮累计值，再除以时间差。
  TCP 多映射代理需要把所有 mapping 的 frps_name 用量相加。
  XTCP 的 stcp fallback 用量计入对应 P2P 代理。

  已用流量达到 traffic_limit_mb 时停用代理。
  用户 balance_mb 小于等于 0 时停用代理。
  已删除代理不再被轮询器恢复为 online。
  管理员停用代理不会释放端口，避免旧脚本端口被其他用户占用。

  actual_local_port 来自 frps 观察到的 localPort，可能与脚本默认值不同。
  last_seen_at 在代理在线时刷新，用于前端展示最后活动时间。
  is_online 只表达 frps 当前观察到的连接状态，不表达权限状态。
  current_speed_bps 在代理离线或未变化时回落为 0。
"""

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
            store_changed = False
            for proxy in store.proxies.values():
                if proxy.status == ProxyStatus.DELETED:
                    continue
                if proxy.proxy_type == ProxyType.TCP:
                    store_changed = (
                        _apply_tcp_poll_info(proxy, by_name, self.interval_sec) or store_changed
                    )
                elif proxy.proxy_type == ProxyType.HTTP:
                    info = by_name.get(proxy.frps_name)
                    store_changed = _apply_poll_info(proxy, info, self.interval_sec) or store_changed
                else:
                    store_changed = (
                        _apply_p2p_poll_info(proxy, by_name, self.interval_sec) or store_changed
                    )
                store_changed = _apply_stop_rules(proxy) or store_changed
            if store_changed:
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
    """@brief 累加代理流量并按完整 MB 扣减用户余额。
    @param proxy 待计费代理。
    @param delta 本轮新增字节数。
    @return 只要流量发生变化就返回 True，提示调用方保存 Store。
    @note 余额以 MB 为单位，未满 1 MB 的尾数保留到后续轮询累计。
    """

    previous_used_bytes = proxy.traffic_used_bytes
    proxy.traffic_used_bytes += delta
    user = store.users.get(proxy.uid)
    if user is not None:
        previous_used_mb = previous_used_bytes // (1024 * 1024)
        current_used_mb = proxy.traffic_used_bytes // (1024 * 1024)
        charged_mb = current_used_mb - previous_used_mb
        if charged_mb > 0:
            user.balance_mb = max(0, user.balance_mb - charged_mb)
    return True


def _apply_stop_rules(proxy: Proxy) -> bool:
    """@brief 根据流量上限和用户余额停用代理。
    @param proxy 待检查代理。
    @return 状态发生变化时返回 True，提示调用方保存 Store。
    @note 停用不释放 TCP 端口，端口释放仍由删除流程负责。
    """

    if proxy.status != ProxyStatus.ACTIVE:
        return False
    if proxy.traffic_used_bytes >= proxy.traffic_limit_mb * 1024 * 1024:
        proxy.status = ProxyStatus.STOPPED_BY_ADMIN
        proxy.is_online = False
        return True
    user = store.users.get(proxy.uid)
    if user is not None and user.balance_mb <= 0:
        proxy.status = ProxyStatus.STOPPED_BY_ADMIN
        proxy.is_online = False
        return True
    return False


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_online(info: dict[str, Any] | None) -> bool:
    if not info:
        return False
    return str(info.get("status", "")) == "online"
