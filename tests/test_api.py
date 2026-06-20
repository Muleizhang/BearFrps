"""@file tests/test_api.py
@brief 验证用户端、管理端、展示页、端口池和脚本生成的主要业务流程。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：FastAPI TestClient、backend.main.app、backend.models。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和测试覆盖说明。
  用户注册、登录、注销、旧 UID 迁移和用户持久化。
  TCP 单端口、多端口、自动端口、端口冲突和范围释放。
  HTTP 代理、子域名、高级配置和公开 URL。
  XTCP 代理、visitor 脚本和 stcp fallback 配置。
  管理员登录、端口池调整、启停删除代理和用户列表。
  展示页只返回 active 且 online 的代理。

  所有接口返回预期状态码和关键字段。
  创建代理后余额扣减、脚本包含必要 frpc 配置。
  删除代理后端口可再次分配。

  test_user_lifecycle_and_scripts 覆盖注册、初始化、充值、创建代理、脚本和删除。
  test_create_tcp_auto_multiple_ports 覆盖自动连续端口分配和多 [[proxies]] 输出。
  test_create_tcp_proxy_with_advanced_transport_config 覆盖加密、压缩和限速模式输出。
  test_create_tcp_single_port_and_occupied_failure 覆盖指定端口占用冲突。
  test_create_tcp_range_validation_and_release 覆盖范围端口、数量限制、本地端口溢出和释放。
  test_create_http_proxy_and_scripts 覆盖 HTTP 公开 URL 和脚本返回。
  test_create_http_proxy_with_advanced_config 覆盖 HTTP 认证、locations 和 host header。
  test_create_xtcp_proxy_and_visitor_scripts 覆盖 XTCP 服务端与 visitor 配置。
  test_create_xtcp_proxy_with_advanced_config 覆盖 XTCP fallback 设置。
  test_create_proxy_advanced_config_validation_errors 覆盖高级配置非法输入。
  test_user_auth_login_logout_and_persistence 覆盖账号持久化和会话清理。
  test_invalid_uid_cookie_does_not_authenticate 覆盖旧 UID cookie 不再直接认证。
  test_register_migrates_legacy_uid_data 覆盖匿名 UID 数据迁移到注册账号。
  test_create_proxy_validation_errors 覆盖名称、余额、连接数和类型错误。
  test_admin_auth_and_operations 覆盖管理员登录和代理状态操作。
  test_show_online_only_returns_active_online 覆盖展示页过滤规则。
  test_admin_config_get_and_update 覆盖端口池读取和扩大范围。
  test_admin_config_update_rejects_invalid_range 覆盖非法端口范围。
  test_admin_config_update_rejects_when_proxy_outside_new_range 覆盖已占用端口越界保护。
  test_admin_port_range_ignores_http_proxies 覆盖 HTTP 代理不占用端口池。
  test_port_pool_update_range 覆盖 PortPool 范围更新。
  test_port_pool_batch_allocate_reserve_release 覆盖批量分配、预留和释放。
  test_port_pool_skips_in_use_port 覆盖本机端口占用跳过逻辑。

  关键接口必须断言 HTTP 状态码。
  代理创建测试必须断言 DTO、frpc_config 和 scripts 三类返回。
  端口相关测试必须断言具体端口值，避免只检查成功状态。
  认证测试必须断言退出后接口变为 401。
  展示页测试通过直接修改 Store 构造 online/offline 场景。

  TestClient 使用 FastAPI lifespan，会加载模板和用户数据。
  conftest 会把持久化文件重定向到 tmp_path。
  所有测试结束后端口池恢复初始范围。

  注册接口返回 uid、username 和余额字段。
  未登录访问 /api/user/me 必须返回 401。
  充值接口返回新的 balance_mb。
  创建代理响应必须包含 proxy、frpc_config、scripts。
  frpc_config 必须包含用户 token metadata。
  TCP 响应必须包含 frps_remote_port 和 tcp_mappings。
  HTTP 响应必须包含 public_url 或 public_urls。
  XTCP 响应必须包含 visitor 配置。
  删除代理响应固定为 {"ok": true}。
  管理端登录失败不能创建 session。
  管理端删除代理后端口池应释放相关端口。
  展示页不能返回 stopped_by_admin 或 offline 代理。

  TCP count 超过 max_tcp_ports_per_proxy 时拒绝。
  remote_start_port 大于 remote_end_port 时拒绝。
  local_start_port 映射后超过 65535 时拒绝。
  已占用 remotePort 再次申请时拒绝。
  用户余额不足时创建代理拒绝。
  用户达到最大连接数时创建代理拒绝。
  同一用户重复代理名拒绝。
  非本人代理删除和脚本获取返回 404。
  管理端端口池缩小不能覆盖 active TCP 代理。
  HTTP 代理不影响端口池缩小。

  用户注册后写入 users.json。
  重启加载用户时补齐 frpc token 字段。
  旧匿名 uid 数据可迁移到注册用户。
  注销后 session 被清理但用户数据保留。
  测试通过 monkeypatch 把持久化文件放到临时目录。

  Linux/macOS/Windows frpc 脚本都应存在。
  demo 脚本都应存在。
  TCP 多端口配置应出现多个 [[proxies]]。
  高级配置应输出 transport.useEncryption。
  HTTP 高级配置应输出 basicAuth 或 locations。
  visitor 配置应输出 bindPort 和 secretKey。
  刷新脚本接口应返回与创建接口兼容的结构。

  覆盖正常流程。
  覆盖异常输入。
  覆盖权限失败。
  覆盖资源释放。
  覆盖持久化迁移。
  覆盖展示页过滤。
  覆盖管理员操作。
  覆盖端口池边界。
  覆盖多代理类型。
  覆盖脚本内容。
  覆盖 frpc token 轮换后的 API 表现。
  覆盖 mock 之外的真实 FastAPI 路由。

  测试用例文档中的“用户生命周期”由本文件覆盖。
  测试用例文档中的“代理创建”由本文件覆盖。
  测试用例文档中的“管理员接口”由本文件覆盖。
  测试用例文档中的“展示页”由本文件覆盖。
  测试用例文档中的“端口池”由本文件覆盖。
  测试结果可作为课程审计记录附件。

  新增用户接口必须新增成功和失败测试。
  新增代理字段必须断言 DTO 和脚本输出。
  修改端口池规则必须补冲突和释放测试。
  修改认证逻辑必须补 401/403 场景。
  修改持久化结构必须补迁移测试。

  本文件证明核心 HTTP API 可自动化验收。
  TestClient 不需要真实监听端口。
  临时文件保证测试不会污染课程提交数据。
@section api_test_doxygen Doxygen 注释约束
  测试文件头说明覆盖范围、断言策略和副作用。
  新增接口测试应说明成功路径和失败路径。
  端口池测试应说明分配、预留和释放规则。
  认证测试应说明 session 和 cookie 行为。
  持久化测试应说明临时文件隔离方式。
@section api_test_submission 平时作业提交检查
  pytest 必须全部通过。
  用户生命周期必须有测试。
  管理员操作必须有测试。
  展示页过滤必须有测试。
  端口池边界必须有测试。
  脚本生成必须有测试。
  错误输入必须有测试。
@section api_test_runtime 运行时约束
  测试运行不需要真实 frps。
  测试运行不需要公网服务器。
  TestClient 会执行 FastAPI lifespan。
  临时目录隔离用户持久化文件。
  端口池在每个测试后重置。
  session 在每个测试前清空。
@section api_test_license 许可证和来源
  测试代码属于 BearFrps 根项目。
  根项目许可证为 Apache-2.0。
  pytest 依赖记录在 SBOM.json。
  测试结果用于课程质量证明。
"""

from __future__ import annotations

import asyncio
import sqlite3

from fastapi.testclient import TestClient

from backend import sqlite_persistence
from backend.deps import port_pool, settings
from backend.main import _reserve_loaded_tcp_ports_unlocked, app
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
        token_response = client.get("/api/user/frpc-token")
        assert token_response.status_code == 200
        frpc_token = token_response.json()["token"]

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
        assert body["proxy"]["token"] == frpc_token
        assert f'auth.token = "{settings.frps_auth_token}"' in body["frpc_config"]
        assert f'metadatas.token = "{frpc_token}"' in body["frpc_config"]
        assert f'metadatas.uid = "{uid}"' in body["frpc_config"]
        assert body["scripts"]["frpc"]["linux"]
        assert client.get("/api/user/me").json()["balance_mb"] == settings.free_recharge_amount_mb - 10

        listed = client.get("/api/proxies")
        assert listed.status_code == 200
        assert len(listed.json()["proxies"]) == 1

        scripts = client.get(f"/api/proxies/{body['proxy']['id']}/scripts")
        assert scripts.status_code == 200
        assert scripts.json()["proxy"]["id"] == body["proxy"]["id"]

        rotated = client.post("/api/user/frpc-token/rotate", json={})
        assert rotated.status_code == 200
        assert rotated.json()["token"] != frpc_token
        assert rotated.json()["version"] == token_response.json()["version"] + 1
        rotated_scripts = client.get(f"/api/proxies/{body['proxy']['id']}/scripts")
        assert rotated_scripts.status_code == 200
        assert f'metadatas.token = "{rotated.json()["token"]}"' in rotated_scripts.json()["frpc_config"]
        assert frpc_token not in rotated_scripts.json()["frpc_config"]

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


def test_create_tcp_proxy_with_advanced_transport_config():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "secure",
                "traffic_mb": 10,
                "speed_limit_kbps": 512,
                "advanced_config": {
                    "use_encryption": True,
                    "use_compression": True,
                    "bandwidth_limit_mode": "client",
                },
            },
        )
        assert created.status_code == 200
        body = created.json()
        proxy = body["proxy"]
        assert proxy["use_encryption"] is True
        assert proxy["use_compression"] is True
        assert proxy["bandwidth_limit_mode"] == "client"
        assert 'transport.bandwidthLimitMode = "client"' in body["frpc_config"]
        assert "transport.useEncryption = true" in body["frpc_config"]
        assert "transport.useCompression = true" in body["frpc_config"]


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
        assert [m["local_port"] for m in created.json()["proxy"]["tcp_mappings"]] == [9000, 9000, 9000]

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

        many_to_many = client.post(
            "/api/proxies",
            json={
                "proxy_type": "tcp",
                "name": "range-many",
                "traffic_mb": 1,
                "tcp_ports": {
                    "mode": "range",
                    "mapping_mode": "many-to-many",
                    "remote_start_port": start + 5,
                    "remote_end_port": start + 6,
                    "local_start_port": 9400,
                },
            },
        )
        assert many_to_many.status_code == 200
        assert [m["local_port"] for m in many_to_many.json()["proxy"]["tcp_mappings"]] == [9400, 9401]

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
                    "mapping_mode": "many-to-many",
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


def test_create_http_proxy_with_advanced_config():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "advanced-site",
                "traffic_mb": 10,
                "local_ip": "localhost",
                "local_port": 8080,
                "subdomain": "advanced-site",
                "advanced_config": {
                    "use_encryption": True,
                    "http_user": "admin",
                    "http_password": "secret",
                    "http_locations": ["/", "/api"],
                    "host_header_rewrite": "example.com:8080",
                },
            },
        )
        assert created.status_code == 200
        body = created.json()
        proxy = body["proxy"]
        assert proxy["http_user"] == "admin"
        assert proxy["http_password"] == "secret"
        assert proxy["http_locations"] == ["/", "/api"]
        assert proxy["host_header_rewrite"] == "example.com:8080"
        assert 'httpUser = "admin"' in body["frpc_config"]
        assert 'httpPassword = "secret"' in body["frpc_config"]
        assert 'locations = ["/", "/api"]' in body["frpc_config"]
        assert 'hostHeaderRewrite = "example.com:8080"' in body["frpc_config"]
        assert "transport.useEncryption = true" in body["frpc_config"]


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


def test_create_xtcp_proxy_with_advanced_config():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "xtcp",
                "name": "phone-advanced",
                "traffic_mb": 10,
                "local_ip": "127.0.0.1",
                "local_port": 8123,
                "visitor_bind_port": 9002,
                "advanced_config": {
                    "use_compression": True,
                    "keep_tunnel_open": False,
                    "fallback_timeout_ms": 1500,
                },
            },
        )
        assert created.status_code == 200
        body = created.json()
        proxy = body["proxy"]
        assert proxy["keep_tunnel_open"] is False
        assert proxy["fallback_timeout_ms"] == 1500
        assert proxy["use_compression"] is True
        assert "transport.useCompression = true" in body["frpc_configs"]["server"]
        assert "keepTunnelOpen = false" in body["frpc_configs"]["visitor"]
        assert "fallbackTimeoutMs = 1500" in body["frpc_configs"]["visitor"]


def test_create_proxy_advanced_config_validation_errors():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        bad_mode = client.post(
            "/api/proxies",
            json={
                "name": "bad-mode",
                "traffic_mb": 1,
                "advanced_config": {"bandwidth_limit_mode": "edge"},
            },
        )
        assert bad_mode.status_code == 400

        bad_auth = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "bad-auth",
                "traffic_mb": 1,
                "local_port": 8080,
                "subdomain": "bad-auth",
                "advanced_config": {"http_user": "admin"},
            },
        )
        assert bad_auth.status_code == 400

        bad_location = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "bad-location",
                "traffic_mb": 1,
                "local_port": 8080,
                "subdomain": "bad-location",
                "advanced_config": {"http_locations": ["api"]},
            },
        )
        assert bad_location.status_code == 400

        bad_timeout = client.post(
            "/api/proxies",
            json={
                "proxy_type": "xtcp",
                "name": "bad-timeout",
                "traffic_mb": 1,
                "local_port": 8123,
                "advanced_config": {"fallback_timeout_ms": 99},
            },
        )
        assert bad_timeout.status_code == 400


def test_update_tcp_proxy_ignores_remote_port_and_updates_local_config():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})
        client.post("/api/user/recharge", json={})

        created = client.post(
            "/api/proxies",
            json={
                "name": "tcp-edit",
                "traffic_mb": 10,
                "tcp_ports": {"mode": "single", "remote_port": 50000, "local_port": 9528},
            },
        )
        assert created.status_code == 200
        proxy = created.json()["proxy"]

        updated = client.patch(
            f"/api/proxies/{proxy['id']}",
            json={
                "name": "tcp-edited",
                "local_ip": "localhost",
                "local_port": 9530,
                "traffic_mb": 12,
                "speed_limit_kbps": 2048,
                "frps_remote_port": 50001,
                "tcp_ports": {"mode": "single", "remote_port": 50001, "local_port": 9530},
                "advanced_config": {
                    "use_encryption": True,
                    "use_compression": True,
                    "bandwidth_limit_mode": "client",
                },
            },
        )
        assert updated.status_code == 200
        body = updated.json()
        proxy = body["proxy"]
        assert proxy["name"] == "tcp-edited"
        assert proxy["local_ip"] == "localhost"
        assert proxy["local_port"] == 9530
        assert proxy["frps_remote_port"] == 50000
        assert proxy["tcp_mappings"][0]["remote_port"] == 50000
        assert proxy["tcp_mappings"][0]["local_port"] == 9530
        assert proxy["traffic_limit_mb"] == 12
        assert proxy["speed_limit_kbps"] == 2048
        assert "remotePort = 50000" in body["frpc_config"]
        assert "remotePort = 50001" not in body["frpc_config"]
        assert "localPort = 9530" in body["frpc_config"]
        assert "transport.useEncryption = true" in body["frpc_config"]
        assert "transport.useCompression = true" in body["frpc_config"]
        assert 'transport.bandwidthLimitMode = "client"' in body["frpc_config"]


def test_update_http_proxy_checks_subdomain_and_updates_http_config():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        first = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "site-a",
                "traffic_mb": 10,
                "local_port": 8080,
                "subdomain": "site-a",
            },
        )
        second = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "site-b",
                "traffic_mb": 10,
                "local_port": 8081,
                "subdomain": "site-b",
            },
        )
        assert first.status_code == 200
        assert second.status_code == 200

        conflict = client.patch(
            f"/api/proxies/{first.json()['proxy']['id']}",
            json={"subdomain": "site-b"},
        )
        assert conflict.status_code == 400

        updated = client.patch(
            f"/api/proxies/{first.json()['proxy']['id']}",
            json={
                "name": "site-edited",
                "local_ip": "localhost",
                "local_port": 9090,
                "subdomain": "site-c",
                "advanced_config": {
                    "http_user": "demo",
                    "http_password": "secret",
                    "http_locations": ["/api"],
                    "host_header_rewrite": "localhost:9090",
                    "use_encryption": True,
                },
            },
        )
        assert updated.status_code == 200
        body = updated.json()
        proxy = body["proxy"]
        assert proxy["subdomain"] == "site-c"
        assert proxy["public_url"].startswith("http://site-c.")
        assert proxy["http_locations"] == ["/api"]
        assert proxy["host_header_rewrite"] == "localhost:9090"
        assert 'subdomain = "site-c"' in body["frpc_config"]
        assert 'locations = ["/api"]' in body["frpc_config"]
        assert 'hostHeaderRewrite = "localhost:9090"' in body["frpc_config"]


def test_update_xtcp_proxy_ignores_handshake_fields():
    with TestClient(app) as client:
        register_user(client)
        client.post("/api/user/recharge", json={})

        created = client.post(
            "/api/proxies",
            json={
                "proxy_type": "xtcp",
                "name": "phone",
                "traffic_mb": 10,
                "local_port": 8123,
                "visitor_bind_port": 9001,
            },
        )
        assert created.status_code == 200
        original = created.json()["proxy"]

        updated = client.patch(
            f"/api/proxies/{original['id']}",
            json={
                "name": "phone-edited",
                "local_ip": "localhost",
                "local_port": 8124,
                "visitor_bind_port": 9100,
                "traffic_mb": 20,
                "speed_limit_kbps": 512,
                "token": "evil-token",
                "metadatas": {"uid": "u_evil"},
                "p2p_secret_key": "evil-secret",
                "advanced_config": {
                    "keep_tunnel_open": False,
                    "fallback_timeout_ms": 1500,
                    "use_compression": True,
                },
            },
        )
        assert updated.status_code == 200
        body = updated.json()
        proxy = body["proxy"]
        assert proxy["name"] == "phone-edited"
        assert proxy["local_ip"] == "localhost"
        assert proxy["local_port"] == 8124
        assert proxy["visitor_bind_port"] == 9100
        assert proxy["p2p_secret_key"] == original["p2p_secret_key"]
        assert proxy["token"] == original["token"]
        assert proxy["traffic_limit_mb"] == 20
        assert proxy["speed_limit_kbps"] == 512
        assert proxy["keep_tunnel_open"] is False
        assert proxy["fallback_timeout_ms"] == 1500
        assert "evil-secret" not in body["frpc_configs"]["visitor"]
        assert "bindPort = 9100" in body["frpc_configs"]["visitor"]
        assert "fallbackTimeoutMs = 1500" in body["frpc_configs"]["visitor"]


def test_sqlite_persists_users_proxies_and_restores_after_restart():
    with TestClient(app) as client:
        registered = register_user(client)
        client.post("/api/user/recharge", json={})
        client.post("/api/user/recharge", json={})
        tcp = client.post(
            "/api/proxies",
            json={
                "name": "tcp-db",
                "traffic_mb": 10,
                "tcp_ports": {"mode": "single", "remote_port": 50000, "local_port": 9528},
            },
        )
        http = client.post(
            "/api/proxies",
            json={
                "proxy_type": "http",
                "name": "http-db",
                "traffic_mb": 10,
                "local_port": 8080,
                "subdomain": "http-db",
            },
        )
        xtcp = client.post(
            "/api/proxies",
            json={
                "proxy_type": "xtcp",
                "name": "xtcp-db",
                "traffic_mb": 10,
                "local_port": 8123,
                "visitor_bind_port": 9001,
            },
        )
        assert tcp.status_code == 200
        assert http.status_code == 200
        assert xtcp.status_code == 200

        with sqlite3.connect(sqlite_persistence._DB_FILE) as conn:
            assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM proxies").fetchone()[0] == 3
            assert conn.execute("SELECT COUNT(*) FROM tcp_mappings").fetchone()[0] == 1

        store.reset()
        port_pool.reset()
        load_registered_users_unlocked(store)
        _reserve_loaded_tcp_ports_unlocked()

        assert registered["uid"] in store.users
        assert len(store.proxies) == 3
        restored_tcp = next(proxy for proxy in store.proxies.values() if proxy.name == "tcp-db")
        restored_http = next(proxy for proxy in store.proxies.values() if proxy.name == "http-db")
        restored_xtcp = next(proxy for proxy in store.proxies.values() if proxy.name == "xtcp-db")
        assert restored_tcp.tcp_mappings[0].remote_port == 50000
        assert restored_http.subdomain == "http-db"
        assert restored_xtcp.visitor_bind_port == 9001
        assert not port_pool.is_port_unreserved(50000)


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
        assert store.users[registered["uid"]].frpc_token
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
