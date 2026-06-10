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
