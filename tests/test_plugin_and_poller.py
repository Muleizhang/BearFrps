"""@file tests/test_plugin_and_poller.py
@brief 验证 frps 插件鉴权、令牌轮换、多端口映射和轮询器流量统计。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：backend.plugin_handler、backend.poller、backend.models。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和测试意图说明。
  Login 事件接受用户级令牌并重写 frps content。
  NewProxy 事件拒绝错误端口、错误 subdomain 和停用代理。
  Ping 事件拒绝旧 token_version，保证轮换令牌后旧配置失效。
  TCP 多端口代理逐个校验 frps_name 和 remotePort。
  XTCP 与 stcp fallback 代理状态和流量统计。
  轮询器按累计流量计算当前速率，并在超额时停用代理。

  使用 FakeClient 模拟 frps admin API，避免依赖真实 frps 进程。
  通过 store.lock 直接构造模型状态，聚焦插件和轮询器规则本身。

  test_plugin_accepts_user_token_and_rewrites_frps_auth 覆盖 Login 成功和 content 改写。
  test_plugin_rejects_wrong_port_or_stopped_proxy 覆盖 TCP 端口不匹配和停用代理拒绝。
  test_plugin_rejects_rotated_token_version 覆盖用户轮换 token 后旧配置被 Ping 拒绝。
  test_plugin_checks_each_tcp_mapping_name_and_port 覆盖 TCP 多映射逐项校验。
  test_plugin_accepts_http_subdomain_and_rejects_mismatch 覆盖 HTTP 子域名匹配和拒绝。
  test_plugin_accepts_xtcp_and_stcp_fallback_names 覆盖 P2P fallback 代理名称兼容。
  test_poller_updates_usage_and_stops_when_limit_reached 覆盖流量统计和超额停用。
  test_poller_aggregates_tcp_mapping_usage 覆盖 TCP 多端口流量聚合。
  test_poller_updates_http_proxy_usage 覆盖 HTTP 代理在线和用量更新。
  test_poller_tracks_xtcp_online_and_charges_only_fallback_stcp 覆盖 XTCP 与 stcp fallback 计费边界。

  login_content 使用 _auth_key 模拟 frp privilege_key。
  plugin_user 模拟 Login 后 frp 在 content 中携带的 user/metas。
  FakeClient 只实现当前测试所需的 frps admin API 方法。
  测试直接调用插件内部处理函数，避免 HTTP 序列化影响鉴权断言。
  轮询器测试直接调用 _poll_once，避免后台任务带来时间不确定性。

  插件测试断言 reject 字段和 reject_reason。
  成功 Login 测试断言 content.user、metas.uid 和 token_version。
  NewProxy 测试断言正确端口允许、错误端口拒绝。
  轮询器测试断言 traffic_used_bytes、current_speed_bps、status 和 is_online。
  超额测试断言代理状态变为 stopped_by_admin。

  Login 输入包含 timestamp 和 privilege_key。
  新版本 Login 还包含 metadatas.token。
  Login 成功后 content.user 被设置为平台 uid。
  NewProxy 输入包含 user、metas、proxy_name 和 remotePort 等字段。
  HTTP NewProxy 输入包含 subdomain 或 customDomains。
  Ping 输入复用 Login 后的 user/metas。
  CloseProxy 输入可通过 proxy_name 找回代理。

  allow 响应包含 reject=false。
  reject 响应包含 reject=true 和 reject_reason。
  modify 响应包含 reject=false、unchange=false 和 content。
  旧 token_version 被拒绝时不会修改 Store 中的代理状态。
  CloseProxy 成功后 is_online=false。

  list_tcp_proxies 模拟 frps TCP 代理列表。
  list_http_proxies 模拟 HTTP 代理列表。
  list_stcp_proxies 模拟 STCP 代理列表。
  list_xtcp_proxies 模拟 XTCP 代理列表。
  FakeClient 返回 todayTrafficIn/todayTrafficOut 等累计字段。
  轮询器以 frps_name 匹配 Store 中的代理。

  在线代理 is_online=true。
  不在 frps 列表中的 active 代理 is_online=false。
  actual_local_port 来自 frps 返回的 localPort。
  traffic_used_bytes 是入站和出站合计。
  current_speed_bps 由两次轮询差值计算。
  超出 traffic_limit_mb 后 status=stopped_by_admin。
  用户余额不足时同样停用代理。

  每个测试由 conftest 自动清理 Store。
  测试中直接构造 User 和 Proxy，避免依赖 API 路由。
  asyncio.run 包裹异步逻辑，保持 pytest 测试函数同步。
  FakeClient 不发真实网络请求，测试结果稳定。

  覆盖 frps Login 事件。
  覆盖 frps NewProxy 事件。
  覆盖 frps Ping 事件。
  覆盖 frps CloseProxy 事件。
  覆盖用户级 token。
  覆盖旧代理 token 兼容。
  覆盖 token_version 轮换。
  覆盖 TCP 多端口映射。
  覆盖 HTTP 子域名。
  覆盖 XTCP 与 stcp fallback。
  覆盖轮询器流量统计。
  覆盖超额停用。

  插件测试对应 frps Server Plugin 鉴权要求。
  轮询器测试对应 frps Admin API 监控和踢人要求。
  token 轮换测试对应安全与合规中的敏感令牌管理。
  多端口测试对应 TCP range/auto 端口池要求。
  fake client 设计对应可测性文档中的接口明确和输入输出可控。

  修改插件事件字段时必须补对应测试。
  修改 token 规则时必须补旧配置拒绝测试。
  修改轮询器计费时必须补流量聚合测试。
  修改 P2P fallback 时必须补 XTCP 与 stcp fallback 场景。
  修改在线状态规则时必须补 is_online 断言。
@section plugin_test_doxygen Doxygen 注释约束
  插件测试文件头说明事件输入、输出和拒绝场景。
  轮询器测试文件头说明 FakeClient 的输入来源。
  token 测试必须说明新旧版本区别。
  多端口测试必须说明 frps_name 与 remotePort 对应关系。
  P2P 测试必须说明 fallback 代理名规则。
@section plugin_test_submission 平时作业提交检查
  Login 事件必须测试。
  NewProxy 事件必须测试。
  Ping 事件必须测试。
  CloseProxy 事件必须测试。
  轮询流量统计必须测试。
  超额停用必须测试。
  token 轮换拒绝必须测试。
@section plugin_test_runtime 运行时约束
  插件测试不需要真实 frps。
  轮询器测试使用 FakeClient。
  Store 状态由测试直接构造。
  异步逻辑通过 asyncio.run 执行。
  每个测试依赖 conftest 自动重置状态。
  测试不访问公网。
@section plugin_test_license 许可证和来源
  测试代码属于 BearFrps 根项目。
  根项目许可证为 Apache-2.0。
  frp 行为通过兼容输入模拟。
  测试结果用于课程质量证明。
"""

from __future__ import annotations

import asyncio

from backend.models import Proxy, ProxyStatus, ProxyType, TcpMapping, User, store
from backend.plugin_handler import _auth_key, _handle_close_proxy, _handle_login, _handle_new_proxy, _handle_ping
from backend.poller import UsagePoller


def login_content(token: str, timestamp: int = 123) -> dict[str, object]:
    return {"timestamp": timestamp, "privilege_key": _auth_key(token, timestamp)}


def plugin_user(uid: str = "u_a1b2c3d4", version: int = 1) -> dict[str, object]:
    return {"user": uid, "metas": {"uid": uid, "token_version": str(version)}}


def test_plugin_accepts_user_token_and_rewrites_frps_auth():
    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(
                uid="u_a1b2c3d4",
                balance_mb=10,
                frpc_token="user-token",
            )
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="demo",
                frps_name="u_a1b2c3d4__1",
                token="user-token",
                frps_remote_port=50000,
                speed_limit_kbps=128,
                bandwidth_limit_mode="client",
                traffic_limit_mb=10,
            )

        login = await _handle_login({**login_content("bearfrps-internal"), "metas": {"token": "user-token"}})
        assert login["reject"] is False
        assert login["unchange"] is False
        assert login["content"]["user"] == "u_a1b2c3d4"
        assert login["content"]["metas"]["token_version"] == "1"
        assert login["content"]["privilege_key"] == _auth_key("bearfrps-internal", 123)

        new_proxy = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1",
                "remote_port": 50000,
            }
        )
        assert new_proxy["reject"] is False
        assert new_proxy["content"]["bandwidth_limit"] == "128KB"
        assert new_proxy["content"]["bandwidth_limit_mode"] == "client"

    asyncio.run(run())


def test_plugin_rejects_wrong_port_or_stopped_proxy():
    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(
                uid="u_a1b2c3d4",
                balance_mb=10,
                frpc_token="user-token",
            )
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="demo",
                frps_name="u_a1b2c3d4__1",
                token="user-token",
                frps_remote_port=50000,
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )

        wrong_port = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1",
                "remote_port": 50001,
            }
        )
        assert wrong_port["reject"] is True

        async with store.lock:
            store.proxies[1].status = ProxyStatus.STOPPED_BY_ADMIN
        stopped = await _handle_login({**login_content("bearfrps-internal"), "metas": {"token": "user-token"}})
        assert stopped["reject"] is True

    asyncio.run(run())


def test_plugin_rejects_rotated_token_version():
    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(
                uid="u_a1b2c3d4",
                balance_mb=10,
                frpc_token="old-token",
                frpc_token_version=1,
            )
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="demo",
                frps_name="u_a1b2c3d4__1",
                token="old-token",
                frps_remote_port=50000,
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )

        old_login = await _handle_login({**login_content("bearfrps-internal"), "metas": {"token": "old-token"}})
        assert old_login["reject"] is False

        async with store.lock:
            user = store.users["u_a1b2c3d4"]
            user.frpc_token = "new-token"
            user.frpc_token_version = 2
            store.sync_user_proxy_tokens_unlocked(user.uid)

        stale_ping = await _handle_ping({"user": plugin_user(version=1)})
        assert stale_ping["reject"] is True
        assert stale_ping["reject_reason"] == "token has been rotated"

        stale_login = await _handle_login({**login_content("bearfrps-internal"), "metas": {"token": "old-token"}})
        assert stale_login["reject"] is True

        fresh_login = await _handle_login({**login_content("bearfrps-internal"), "metas": {"token": "new-token"}})
        assert fresh_login["reject"] is False
        assert fresh_login["content"]["metas"]["token_version"] == "2"

    asyncio.run(run())


def test_plugin_checks_each_tcp_mapping_name_and_port():
    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(
                uid="u_a1b2c3d4",
                balance_mb=10,
                frpc_token="multi-token",
            )
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="game",
                frps_name="u_a1b2c3d4__1",
                token="multi-token",
                frps_remote_port=50000,
                local_port=8000,
                tcp_mappings=[
                    TcpMapping(frps_name="u_a1b2c3d4__1", remote_port=50000, local_port=8000),
                    TcpMapping(frps_name="u_a1b2c3d4__1__2", remote_port=50001, local_port=8001),
                ],
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )

        ok = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1__2",
                "remote_port": 50001,
            }
        )
        assert ok["reject"] is False

        wrong_port = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1__2",
                "remote_port": 50000,
            }
        )
        assert wrong_port["reject"] is True

        wrong_name = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1__3",
                "remote_port": 50002,
            }
        )
        assert wrong_name["reject"] is True

    asyncio.run(run())


def test_plugin_accepts_http_subdomain_and_rejects_mismatch():
    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(
                uid="u_a1b2c3d4",
                balance_mb=10,
                frpc_token="http-token",
            )
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="site",
                frps_name="u_a1b2c3d4__1",
                token="http-token",
                proxy_type=ProxyType.HTTP,
                local_port=8080,
                subdomain="site",
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )

        ok = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1",
                "proxy_type": "http",
                "subdomain": "site",
            }
        )
        assert ok["reject"] is False
        assert ok["content"]["bandwidth_limit"] == "128KB"

        bad = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1",
                "proxy_type": "http",
                "subdomain": "other",
            }
        )
        assert bad["reject"] is True

    asyncio.run(run())


def test_plugin_accepts_xtcp_and_stcp_fallback_names():
    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(
                uid="u_a1b2c3d4",
                balance_mb=10,
                frpc_token="p2p-token",
            )
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="phone",
                frps_name="u_a1b2c3d4__1",
                token="p2p-token",
                proxy_type=ProxyType.XTCP,
                local_port=8123,
                p2p_secret_key="secret",
                p2p_fallback_name="u_a1b2c3d4__1__fallback",
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )

        xtcp = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1",
                "proxy_type": "xtcp",
            }
        )
        assert xtcp["reject"] is False
        assert xtcp["content"]["bandwidth_limit"] == "128KB"

        fallback = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1__fallback",
                "proxy_type": "stcp",
            }
        )
        assert fallback["reject"] is False

        wrong_type = await _handle_new_proxy(
            {
                "user": plugin_user(),
                "proxy_name": "u_a1b2c3d4__1__fallback",
                "proxy_type": "xtcp",
            }
        )
        assert wrong_type["reject"] is True

        await _handle_close_proxy({"proxy_name": "u_a1b2c3d4__1"})
        async with store.lock:
            assert store.proxies[1].is_online is True
            assert store.proxies[1].p2p_xtcp_is_online is False
            assert store.proxies[1].p2p_fallback_is_online is True

    asyncio.run(run())


def test_poller_updates_usage_and_stops_when_limit_reached():
    class FakeClient:
        async def list_tcp_proxies(self):
            return [
                {
                    "name": "u_a1b2c3d4__1",
                    "status": "online",
                    "todayTrafficIn": 1024 * 1024,
                    "todayTrafficOut": 0,
                    "conf": {"localPort": 8080},
                }
            ]

    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(uid="u_a1b2c3d4", balance_mb=10)
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="demo",
                frps_name="u_a1b2c3d4__1",
                token="user-token",
                frps_remote_port=50000,
                speed_limit_kbps=128,
                traffic_limit_mb=1,
            )
            store.proxies[1].last_frps_total_bytes = 0

        poller = UsagePoller(FakeClient(), interval_sec=2)
        await poller.poll_once()

        async with store.lock:
            proxy = store.proxies[1]
            user = store.users["u_a1b2c3d4"]
            assert proxy.actual_local_port == 8080
            assert proxy.traffic_used_bytes == 1024 * 1024
            assert proxy.current_speed_bps == 512 * 1024
            assert proxy.status == ProxyStatus.STOPPED_BY_ADMIN
            assert user.balance_mb == 9

    asyncio.run(run())


def test_poller_aggregates_tcp_mapping_usage():
    class FakeClient:
        async def list_tcp_proxies(self):
            return [
                {
                    "name": "u_a1b2c3d4__1",
                    "status": "online",
                    "todayTrafficIn": 1024 * 1024,
                    "todayTrafficOut": 0,
                    "conf": {"localPort": 8000},
                },
                {
                    "name": "u_a1b2c3d4__1__2",
                    "status": "online",
                    "todayTrafficIn": 512 * 1024,
                    "todayTrafficOut": 512 * 1024,
                    "conf": {"localPort": 8001},
                },
            ]

    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(uid="u_a1b2c3d4", balance_mb=10)
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="game",
                frps_name="u_a1b2c3d4__1",
                token="multi-token",
                frps_remote_port=50000,
                local_port=8000,
                tcp_mappings=[
                    TcpMapping(
                        frps_name="u_a1b2c3d4__1",
                        remote_port=50000,
                        local_port=8000,
                        last_frps_total_bytes=0,
                    ),
                    TcpMapping(
                        frps_name="u_a1b2c3d4__1__2",
                        remote_port=50001,
                        local_port=8001,
                        last_frps_total_bytes=0,
                    ),
                ],
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )

        poller = UsagePoller(FakeClient(), interval_sec=2)
        await poller.poll_once()

        async with store.lock:
            proxy = store.proxies[1]
            user = store.users["u_a1b2c3d4"]
            assert proxy.is_online is True
            assert [m.actual_local_port for m in proxy.tcp_mappings] == [8000, 8001]
            assert proxy.traffic_used_bytes == 2 * 1024 * 1024
            assert proxy.current_speed_bps == 1024 * 1024
            assert user.balance_mb == 8

    asyncio.run(run())


def test_poller_updates_http_proxy_usage():
    class FakeClient:
        async def list_tcp_proxies(self):
            return []

        async def list_http_proxies(self):
            return [
                {
                    "name": "u_a1b2c3d4__1",
                    "status": "online",
                    "todayTrafficIn": 512 * 1024,
                    "todayTrafficOut": 512 * 1024,
                    "conf": {"localPort": 8080},
                }
            ]

    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(uid="u_a1b2c3d4", balance_mb=10)
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="site",
                frps_name="u_a1b2c3d4__1",
                token="http-token",
                proxy_type=ProxyType.HTTP,
                local_port=8080,
                subdomain="site",
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )
            store.proxies[1].last_frps_total_bytes = 0

        poller = UsagePoller(FakeClient(), interval_sec=2)
        await poller.poll_once()

        async with store.lock:
            proxy = store.proxies[1]
            assert proxy.is_online is True
            assert proxy.actual_local_port == 8080
            assert proxy.traffic_used_bytes == 1024 * 1024
            assert proxy.current_speed_bps == 512 * 1024

    asyncio.run(run())


def test_poller_tracks_xtcp_online_and_charges_only_fallback_stcp():
    class FakeClient:
        async def list_tcp_proxies(self):
            return []

        async def list_http_proxies(self):
            return []

        async def list_stcp_proxies(self):
            return [
                {
                    "name": "u_a1b2c3d4__1__fallback",
                    "status": "online",
                    "todayTrafficIn": 1024 * 1024,
                    "todayTrafficOut": 0,
                    "conf": {"localPort": 8123},
                }
            ]

        async def list_xtcp_proxies(self):
            return [
                {
                    "name": "u_a1b2c3d4__1",
                    "status": "online",
                    "todayTrafficIn": 100 * 1024 * 1024,
                    "todayTrafficOut": 100 * 1024 * 1024,
                }
            ]

    async def run():
        async with store.lock:
            store.users["u_a1b2c3d4"] = User(uid="u_a1b2c3d4", balance_mb=10)
            store.proxies[1] = Proxy(
                id=1,
                uid="u_a1b2c3d4",
                name="phone",
                frps_name="u_a1b2c3d4__1",
                token="p2p-token",
                proxy_type=ProxyType.XTCP,
                local_port=8123,
                p2p_secret_key="secret",
                p2p_fallback_name="u_a1b2c3d4__1__fallback",
                speed_limit_kbps=128,
                traffic_limit_mb=10,
            )
            store.proxies[1].last_frps_total_bytes = 0

        poller = UsagePoller(FakeClient(), interval_sec=2)
        await poller.poll_once()

        async with store.lock:
            proxy = store.proxies[1]
            user = store.users["u_a1b2c3d4"]
            assert proxy.is_online is True
            assert proxy.p2p_xtcp_is_online is True
            assert proxy.p2p_fallback_is_online is True
            assert proxy.traffic_used_bytes == 1024 * 1024
            assert proxy.current_speed_bps == 512 * 1024
            assert user.balance_mb == 9

    asyncio.run(run())
