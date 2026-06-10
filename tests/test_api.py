from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.deps import settings
from backend.main import app
from backend.auth import clear_all_user_sessions
from backend.models import Proxy, ProxyStatus, store
from backend.user_persistence import load_registered_users_unlocked


def register_user(client: TestClient, username: str = "alice", password: str = "password123") -> dict[str, object]:
    response = client.post(
        "/api/user/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()


def test_user_lifecycle_and_scripts():
    with TestClient(app) as client:
        assert client.get("/api/user/me").status_code == 401

        registered = register_user(client)
        uid = registered["uid"]
        assert uid.startswith("u_")
        assert registered["username"] == "alice"

        init = client.post("/api/user/init", json={})
        assert init.status_code == 200
        assert init.json()["uid"] == uid

        recharge = client.post("/api/user/recharge", json={})
        assert recharge.status_code == 200
        assert recharge.json()["balance_mb"] == settings.free_recharge_amount_mb

        created = client.post(
            "/api/proxies",
            json={"name": "demo", "traffic_mb": 10, "speed_limit_kbps": 512},
        )
        assert created.status_code == 200
        body = created.json()
        assert body["proxy"]["name"] == "demo"
        assert body["proxy"]["frps_remote_port"] == settings.allocatable_port_range_start
        assert body["proxy"]["tcp_mappings"][0]["remote_port"] == settings.allocatable_port_range_start
        assert body["proxy"]["public_urls"] == [body["proxy"]["public_url"]]
        assert "metadatas.token" in body["frpc_config"]
        assert body["scripts"]["frpc"]["linux"]
        assert client.get("/api/user/me").json()["balance_mb"] == settings.free_recharge_amount_mb - 10

        listed = client.get("/api/proxies")
        assert listed.status_code == 200
        assert len(listed.json()["proxies"]) == 1

        scripts = client.get(f"/api/proxies/{body['proxy']['id']}/scripts")
        assert scripts.status_code == 200
        assert scripts.json()["proxy"]["id"] == body["proxy"]["id"]

        deleted = client.delete(f"/api/proxies/{body['proxy']['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}


def test_create_tcp_auto_multiple_ports():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "game",
                "traffic_mb": 10,
                "speed_limit_kbps": 512,
                "local_ip": "127.0.0.1",
                "tcp_ports": {
                    "mode": "auto",
                    "count": 3,
                    "local_start_port": 8000,
                },
            },
        )
        assert created.status_code == 200
        body = created.json()
        mappings = body["proxy"]["tcp_mappings"]
        assert [m["remote_port"] for m in mappings] == [
            settings.allocatable_port_range_start,
            settings.allocatable_port_range_start + 1,
            settings.allocatable_port_range_start + 2,
        ]
        assert [m["local_port"] for m in mappings] == [8000, 8001, 8002]
        assert body["proxy"]["frps_remote_port"] == settings.allocatable_port_range_start
        assert body["proxy"]["local_port"] == 8000
        assert len(body["proxy"]["public_urls"]) == 3
        assert body["frpc_config"].count("[[proxies]]") == 3
        assert "remotePort = 50000" in body["frpc_config"]
        assert "localPort = 8002" in body["frpc_config"]


def test_create_tcp_single_port_and_occupied_failure():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        port = settings.allocatable_port_range_start + 10

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "ssh",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "single",
                    "remote_port": port,
                    "local_port": 22,
                },
            },
        )
        assert created.status_code == 200
        assert created.json()["proxy"]["frps_remote_port"] == port
        assert created.json()["proxy"]["local_port"] == 22

        duplicate = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "ssh2",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "single",
                    "remote_port": port,
                    "local_port": 2222,
                },
            },
        )
        assert duplicate.status_code == 400
        assert str(port) in duplicate.json()["detail"]


def test_create_tcp_range_validation_and_release():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        start = settings.allocatable_port_range_start + 20

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "range",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "range",
                    "remote_start_port": start,
                    "remote_end_port": start + 2,
                    "local_start_port": 9000,
                },
            },
        )
        assert created.status_code == 200
        proxy_id = created.json()["proxy"]["id"]
        assert [m["remote_port"] for m in created.json()["proxy"]["tcp_mappings"]] == [
            start,
            start + 1,
            start + 2,
        ]

        partial_conflict = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "range2",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "range",
                    "remote_start_port": start + 2,
                    "remote_end_port": start + 3,
                    "local_start_port": 9100,
                },
            },
        )
        assert partial_conflict.status_code == 400
        assert str(start + 2) in partial_conflict.json()["detail"]

        too_many = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "too-many",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "auto",
                    "count": settings.max_tcp_ports_per_proxy + 1,
                    "local_start_port": 9200,
                },
            },
        )
        assert too_many.status_code == 400

        local_overflow = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "overflow",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "range",
                    "remote_start_port": start + 10,
                    "remote_end_port": start + 11,
                    "local_start_port": 65535,
                },
            },
        )
        assert local_overflow.status_code == 400

        deleted = client.delete(f"/api/proxies/{proxy_id}")
        assert deleted.status_code == 200
        recreated = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "range3",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "range",
                    "remote_start_port": start,
                    "remote_end_port": start + 2,
                    "local_start_port": 9300,
                },
            },
        )
        assert recreated.status_code == 200


def test_create_http_proxy_and_scripts():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "site",
                "traffic_mb": 10,
                "speed_limit_kbps": 256,
                "local_ip": "localhost",
                "local_port": 8080,
                "subdomain": "site",
            },
        )
        assert created.status_code == 200
        body = created.json()
        assert body["proxy"]["proxy_type"] == "http"
        assert body["proxy"]["frps_remote_port"] is None
        assert body["proxy"]["local_ip"] == "localhost"
        assert body["proxy"]["local_port"] == 8080
        assert body["proxy"]["subdomain"] == "site"
        assert body["proxy"]["public_url"].startswith("http://site.")
        assert f":{settings.frps_vhost_http_port}/" in body["proxy"]["public_url"]
        assert 'type = "http"' in body["frpc_config"]
        assert 'localIP = "localhost"' in body["frpc_config"]
        assert "localPort = 8080" in body["frpc_config"]
        assert 'subdomain = "site"' in body["frpc_config"]
        assert "remotePort" not in body["frpc_config"]
        assert 'type = "http"' in body["scripts"]["frpc"]["linux"]

        duplicate = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "site2",
                "traffic_mb": 1,
                "local_port": 8081,
                "subdomain": "site",
            },
        )
        assert duplicate.status_code == 400


def test_create_xtcp_proxy_and_visitor_scripts():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        before_balance = client.get("/api/user/me").json()["balance_mb"]

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "xtcp",
                "name": "phone",
                "traffic_mb": 10,
                "speed_limit_kbps": 256,
                "local_ip": "127.0.0.1",
                "local_port": 8123,
                "visitor_bind_port": 9001,
            },
        )
        assert created.status_code == 200
        body = created.json()
        proxy = body["proxy"]
        assert proxy["proxy_type"] == "xtcp"
        assert proxy["frps_remote_port"] is None
        assert proxy["tcp_mappings"] == []
        assert proxy["public_url"] is None
        assert proxy["public_urls"] == []
        assert proxy["visitor_endpoint"] == "127.0.0.1:9001"
        assert proxy["p2p_fallback_name"] == f"{proxy['frps_name']}__fallback"
        assert client.get("/api/user/me").json()["balance_mb"] == before_balance

        server_config = body["frpc_configs"]["server"]
        visitor_config = body["frpc_configs"]["visitor"]
        assert body["frpc_config"] == server_config
        assert 'type = "xtcp"' in server_config
        assert 'type = "stcp"' in server_config
        assert "remotePort" not in server_config
        assert "localPort = 8123" in server_config
        assert '[[visitors]]' in visitor_config
        assert 'type = "xtcp"' in visitor_config
        assert 'type = "stcp"' in visitor_config
        assert 'fallbackTo = "' in visitor_config
        assert "keepTunnelOpen = true" in visitor_config
        assert "bindPort = 9001" in visitor_config
        assert "bindPort = -1" in visitor_config
        assert body["scripts"]["visitor"]["linux"]


def test_user_auth_login_logout_and_persistence():
    with TestClient(app) as client:
        registered = register_user(client, username="persisted")
        client.post("/api/user/recharge", json={})

        duplicate = client.post(
            "/api/user/register",
            json={"username": "Persisted", "password": "password123"},
        )
        assert duplicate.status_code == 400

        bad_login = client.post(
            "/api/user/login",
            json={"username": "persisted", "password": "wrong-password"},
        )
        assert bad_login.status_code == 401

        logout = client.post("/api/user/logout", json={})
        assert logout.status_code == 200
        assert client.get("/api/user/me").status_code == 401

        login = client.post(
            "/api/user/login",
            json={"username": "PERSISTED", "password": "password123"},
        )
        assert login.status_code == 200
        assert login.json()["uid"] == registered["uid"]
        assert login.json()["balance_mb"] == settings.free_recharge_amount_mb

        clear_all_user_sessions()
        store.reset()

        async def reload_users():
            async with store.lock:
                load_registered_users_unlocked(store)

        asyncio.run(reload_users())
        login_after_reload = client.post(
            "/api/user/login",
            json={"username": "persisted", "password": "password123"},
        )
        assert login_after_reload.status_code == 200
        assert login_after_reload.json()["balance_mb"] == settings.free_recharge_amount_mb


def test_invalid_uid_cookie_does_not_authenticate():
    with TestClient(app) as client:
        client.cookies.set("uid", "not-valid")
        assert client.get("/api/user/me").status_code == 401
        registered = register_user(client)
        assert registered["uid"].startswith("u_")
        assert registered["uid"] != "not-valid"


def test_register_migrates_legacy_uid_data():
    with TestClient(app) as client:
        async def seed_legacy_user():
            async with store.lock:
                legacy = store.ensure_user_unlocked("u_a1b2c3d4")
                legacy.balance_mb = 25
                store.proxies[1] = Proxy(
                    id=1,
                    uid=legacy.uid,
                    name="legacy",
                    frps_name="u_a1b2c3d4__1",
                    token="legacy-token",
                    frps_remote_port=50000,
                    speed_limit_kbps=128,
                    traffic_limit_mb=5,
                )

        asyncio.run(seed_legacy_user())
        client.cookies.set("uid", "u_a1b2c3d4")

        registered = register_user(client, username="legacy")
        assert registered["uid"] == "u_a1b2c3d4"
        assert registered["balance_mb"] == 25

        listed = client.get("/api/proxies")
        assert listed.status_code == 200
        assert listed.json()["proxies"][0]["name"] == "legacy"


def test_create_proxy_validation_errors():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        too_much = client.post("/api/proxies", json={"name": "x", "traffic_mb": 9999})
        assert too_much.status_code == 400

        first = client.post("/api/proxies", json={"name": "x", "traffic_mb": 1})
        assert first.status_code == 200

        dup = client.post("/api/proxies", json={"name": "x", "traffic_mb": 1})
        assert dup.status_code == 400


def test_admin_auth_and_operations():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        created = client.post("/api/proxies", json={"name": "demo", "traffic_mb": 1}).json()
        proxy_id = created["proxy"]["id"]

        assert client.get("/api/admin/proxies").status_code == 401
        bad = client.post("/api/admin/login", json={"username": "admin", "password": "bad"})
        assert bad.status_code == 401
        ok = client.post(
            "/api/admin/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert ok.status_code == 200

        proxies = client.get("/api/admin/proxies")
        assert proxies.status_code == 200
        assert proxies.json()["proxies"][0]["uid"].startswith("u_")

        stopped = client.post(f"/api/admin/proxies/{proxy_id}/stop")
        assert stopped.status_code == 200
        assert client.get("/api/admin/proxies").json()["proxies"][0]["status"] == "stopped_by_admin"

        started = client.post(f"/api/admin/proxies/{proxy_id}/start")
        assert started.status_code == 200
        assert client.get("/api/admin/proxies").json()["proxies"][0]["status"] == "active"

        users = client.get("/api/admin/users")
        assert users.status_code == 200
        assert users.json()["users"][0]["connection_count"] == 1
        assert users.json()["users"][0]["username"] == "alice"


def test_show_online_only_returns_active_online():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        created = client.post("/api/proxies", json={"name": "demo", "traffic_mb": 1}).json()
        proxy_id = created["proxy"]["id"]

        assert client.get("/api/show/online").json() == {"proxies": []}

        # Mutate under the lock in a small async helper because TestClient tests are sync.
        import asyncio

        async def mark_online():
            async with store.lock:
                proxy = store.proxies[proxy_id]
                proxy.is_online = True
                proxy.status = ProxyStatus.ACTIVE

        asyncio.run(mark_online())
        online = client.get("/api/show/online")
        assert online.status_code == 200
        assert online.json()["proxies"][0]["public_url"].endswith(
            f":{created['proxy']['frps_remote_port']}/"
        )


def test_admin_config_get_and_update():
    with TestClient(app) as client:
        # Login
        ok = client.post(
            "/api/admin/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert ok.status_code == 200

        # Get current config
        cfg = client.get("/api/admin/config")
        assert cfg.status_code == 200
        data = cfg.json()
        assert data["allocatable_port_range_start"] == settings.allocatable_port_range_start
        assert data["allocatable_port_range_end"] == settings.allocatable_port_range_end
        assert data["available_port_count"] > 0

        # Update to a larger range
        put = client.put(
            "/api/admin/config",
            json={"start": settings.allocatable_port_range_start, "end": settings.allocatable_port_range_end + 10},
        )
        assert put.status_code == 200

        cfg2 = client.get("/api/admin/config")
        assert cfg2.json()["allocatable_port_range_end"] == settings.allocatable_port_range_end + 10
        assert cfg2.json()["allocatable_port_range_start"] == settings.allocatable_port_range_start


def test_admin_config_update_rejects_invalid_range():
    with TestClient(app) as client:
        ok = client.post(
            "/api/admin/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert ok.status_code == 200

        # start > end
        bad = client.put("/api/admin/config", json={"start": 100, "end": 50})
        assert bad.status_code == 400

        # out of bounds
        bad2 = client.put("/api/admin/config", json={"start": 0, "end": 100})
        assert bad2.status_code == 400

        bad3 = client.put("/api/admin/config", json={"start": 60000, "end": 70000})
        assert bad3.status_code == 400


def test_admin_config_update_rejects_when_proxy_outside_new_range():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        created = client.post("/api/proxies", json={"name": "test", "traffic_mb": 1})
        assert created.status_code == 200
        port = created.json()["proxy"]["frps_remote_port"]

        ok = client.post(
            "/api/admin/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert ok.status_code == 200

        # Try to shrink range so that the allocated port is outside
        bad = client.put("/api/admin/config", json={"start": port + 1, "end": port + 10})
        assert bad.status_code == 400
        assert "新区间不覆盖" in bad.json()["detail"]


def test_admin_port_range_ignores_http_proxies():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "site",
                "traffic_mb": 1,
                "local_port": 8080,
                "subdomain": "site",
            },
        )
        assert created.status_code == 200
        proxy_id = created.json()["proxy"]["id"]

        ok = client.post(
            "/api/admin/login",
            json={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert ok.status_code == 200

        put = client.put("/api/admin/config", json={"start": 50010, "end": 50020})
        assert put.status_code == 200

        stopped = client.post(f"/api/admin/proxies/{proxy_id}/stop")
        assert stopped.status_code == 200
        started = client.post(f"/api/admin/proxies/{proxy_id}/start")
        assert started.status_code == 200


def test_port_pool_update_range():
    from backend.port_pool import PortPool
    pool = PortPool(50000, 50003)

    p1 = pool.allocate()
    p2 = pool.allocate()
    assert p1 is not None
    assert p2 is not None
    assert p1 != p2

    pool.update_range(50000, 50005, {p1, p2})
    assert pool.get_range() == (50000, 50005)
    assert pool.available_count() == 4

    p3 = pool.allocate()
    assert p3 == 50002


def test_port_pool_batch_allocate_reserve_release():
    from backend.port_pool import PortPool
    pool = PortPool(50000, 50005)

    assert pool.allocate_contiguous(3) == [50000, 50001, 50002]
    assert pool.reserve_many([50004, 50005]) == []
    assert pool.reserve_many([50003, 50004]) == [50004]
    assert pool.allocate() == 50003
    assert pool.allocate() is None

    pool.release_many([50001, 50002])
    assert pool.allocate_contiguous(2) == [50001, 50002]


def test_port_pool_skips_in_use_port(monkeypatch):
    from backend.port_pool import PortPool, _is_port_in_use
    pool = PortPool(50000, 50002)

    # Make port 50000 appear "in use"
    def fake_in_use(port):
        return port == 50000
    monkeypatch.setattr("backend.port_pool._is_port_in_use", fake_in_use)

    p = pool.allocate()
    # 50000 is in use, should skip to 50001
    assert p == 50001
