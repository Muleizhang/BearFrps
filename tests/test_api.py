from __future__ import annotations

from fastapi.testclient import TestClient

from backend.deps import settings
from backend.main import app
from backend.models import ProxyStatus, store


def test_user_lifecycle_and_scripts():
    with TestClient(app) as client:
        init = client.post("/api/user/init", json={})
        assert init.status_code == 200
        uid = init.json()["uid"]
        assert uid.startswith("u_")

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
        assert "metadatas.token" in body["frpc_config"]
        assert body["scripts"]["frpc"]["linux"]

        listed = client.get("/api/proxies")
        assert listed.status_code == 200
        assert len(listed.json()["proxies"]) == 1

        scripts = client.get(f"/api/proxies/{body['proxy']['id']}/scripts")
        assert scripts.status_code == 200
        assert scripts.json()["proxy"]["id"] == body["proxy"]["id"]

        deleted = client.delete(f"/api/proxies/{body['proxy']['id']}")
        assert deleted.status_code == 200
        assert deleted.json() == {"ok": True}


def test_invalid_uid_cookie_is_replaced():
    with TestClient(app) as client:
        client.cookies.set("uid", "not-valid")
        init = client.post("/api/user/init", json={})
        assert init.status_code == 200
        assert init.json()["uid"].startswith("u_")
        assert init.json()["uid"] != "not-valid"


def test_create_proxy_validation_errors():
    with TestClient(app) as client:
        client.post("/api/user/init", json={})
        client.post("/api/user/recharge", json={})

        too_much = client.post("/api/proxies", json={"name": "x", "traffic_mb": 9999})
        assert too_much.status_code == 400

        first = client.post("/api/proxies", json={"name": "x", "traffic_mb": 1})
        assert first.status_code == 200

        dup = client.post("/api/proxies", json={"name": "x", "traffic_mb": 1})
        assert dup.status_code == 400


def test_admin_auth_and_operations():
    with TestClient(app) as client:
        client.post("/api/user/init", json={})
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


def test_show_online_only_returns_active_online():
    with TestClient(app) as client:
        client.post("/api/user/init", json={})
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
        client.post("/api/user/init", json={})
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
