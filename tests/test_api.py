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
        assert body["proxy"]["frps_remote_port"] == settings.remote_port_range_start
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
