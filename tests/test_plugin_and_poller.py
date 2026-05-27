from __future__ import annotations

import asyncio

from backend.models import Proxy, ProxyStatus, User, store
from backend.plugin_handler import _handle_login, _handle_new_proxy
from backend.poller import UsagePoller


def test_plugin_accepts_user_token_and_rewrites_frps_auth():
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
                traffic_limit_mb=10,
            )

        login = await _handle_login(
            {"timestamp": 123, "metas": {"token": "user-token"}, "privilege_key": "old"}
        )
        assert login["reject"] is False
        assert login["unchange"] is True

        new_proxy = await _handle_new_proxy(
            {
                "user": {"metas": {"token": "user-token"}},
                "proxy_name": "u_a1b2c3d4__1",
                "remote_port": 50000,
            }
        )
        assert new_proxy["reject"] is False
        assert new_proxy["content"]["bandwidth_limit"] == "128KB"

    asyncio.run(run())


def test_plugin_rejects_wrong_port_or_stopped_proxy():
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
                traffic_limit_mb=10,
            )

        wrong_port = await _handle_new_proxy(
            {
                "user": {"metas": {"token": "user-token"}},
                "proxy_name": "u_a1b2c3d4__1",
                "remote_port": 50001,
            }
        )
        assert wrong_port["reject"] is True

        async with store.lock:
            store.proxies[1].status = ProxyStatus.STOPPED_BY_ADMIN
        stopped = await _handle_login({"metas": {"token": "user-token"}})
        assert stopped["reject"] is True

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
