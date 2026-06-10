"""@file backend/config.py
@brief 集中定义后端、frps、端口池、计费和管理员账号的环境变量配置。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：python-dotenv、pydantic BaseModel、标准库 pathlib/os。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和配置字段说明。
  所有部署相关默认值都集中在 Settings，路由和业务模块不得硬编码端口。
  .env 只覆盖非空环境变量，空字符串会回退到默认值，减少课堂演示误配置。
  frps_auth_token 是 frps 内部控制通道令牌，不等同于用户级 frpc_token。
  allocatable_port_range_* 是平台可分配公网端口池，不包含用户本地端口。
  max_tcp_ports_per_proxy 限制单个 TCP 代理可申请的映射数量，避免占满端口池。

  get_settings 会读取项目根目录 .env，并通过 lru_cache 保持进程内单例。
  测试若需要替换配置，应在导入依赖前调整环境或使用专门 fixture。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    server_public_host: str = "120.46.51.131"
    backend_port: int = 8000

    frps_version: str = "v0.58.1"
    frps_bind_port: int = 7000
    frps_admin_api_url: str = "http://127.0.0.1:7500"
    frps_admin_user: str = "admin"
    frps_admin_password: str = "changeme"
    frps_auth_token: str = "bearfrps-internal"
    frps_vhost_http_port: int = 8080
    frps_public_vhost_http_port: int = 0
    frps_subdomain_host: str = ""
    frps_nathole_analysis_data_reserve_hours: int = 168

    plugin_path: str = "/frps-plugin"
    remote_port_range_start: int = 1
    remote_port_range_end: int = 65535
    allocatable_port_range_start: int = 50000
    allocatable_port_range_end: int = 50100
    default_local_port: int = 9527
    max_tcp_ports_per_proxy: int = 10

    free_recharge_amount_mb: int = 100
    default_speed_limit_kbps: int = 1024
    usage_poll_interval_sec: int = 2

    admin_username: str = "admin"
    admin_password: str = "changeme"
    max_connections_per_user: int = 3

    demo_bin_base_url_override: str = ""

    @property
    def frp_version_without_v(self) -> str:
        return self.frps_version[1:] if self.frps_version.startswith("v") else self.frps_version

    @property
    def public_vhost_http_port(self) -> int:
        return self.frps_public_vhost_http_port or self.frps_vhost_http_port

    @property
    def demo_bin_base_url(self) -> str:
        if self.demo_bin_base_url_override:
            return self.demo_bin_base_url_override
        return f"http://{self.server_public_host}:{self.backend_port}/static/demo-server-bin"

    @property
    def effective_subdomain_host(self) -> str:
        return self.frps_subdomain_host or self.server_public_host

    @property
    def plugin_addr(self) -> str:
        return f"127.0.0.1:{self.backend_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(ROOT_DIR / ".env")
    defaults = Settings()
    return Settings(
        server_public_host=_env_str("SERVER_PUBLIC_HOST", defaults.server_public_host),
        backend_port=_env_int("BACKEND_PORT", defaults.backend_port),
        frps_version=_env_str("FRPS_VERSION", defaults.frps_version),
        frps_bind_port=_env_int("FRPS_BIND_PORT", defaults.frps_bind_port),
        frps_admin_api_url=_env_str("FRPS_ADMIN_API_URL", defaults.frps_admin_api_url),
        frps_admin_user=_env_str("FRPS_ADMIN_USER", defaults.frps_admin_user),
        frps_admin_password=_env_str("FRPS_ADMIN_PASSWORD", defaults.frps_admin_password),
        frps_auth_token=_env_str("FRPS_AUTH_TOKEN", defaults.frps_auth_token),
        frps_vhost_http_port=_env_int(
            "FRPS_VHOST_HTTP_PORT", defaults.frps_vhost_http_port
        ),
        frps_public_vhost_http_port=_env_int(
            "FRPS_PUBLIC_VHOST_HTTP_PORT", defaults.frps_public_vhost_http_port
        ),
        frps_subdomain_host=_env_str(
            "FRPS_SUBDOMAIN_HOST", defaults.frps_subdomain_host
        ),
        frps_nathole_analysis_data_reserve_hours=_env_int(
            "FRPS_NATHOLE_ANALYSIS_DATA_RESERVE_HOURS",
            defaults.frps_nathole_analysis_data_reserve_hours,
        ),
        plugin_path=_env_str("PLUGIN_PATH", defaults.plugin_path),
        remote_port_range_start=_env_int(
            "REMOTE_PORT_RANGE_START", defaults.remote_port_range_start
        ),
        remote_port_range_end=_env_int("REMOTE_PORT_RANGE_END", defaults.remote_port_range_end),
        allocatable_port_range_start=_env_int(
            "ALLOCATABLE_PORT_RANGE_START", defaults.allocatable_port_range_start
        ),
        allocatable_port_range_end=_env_int(
            "ALLOCATABLE_PORT_RANGE_END", defaults.allocatable_port_range_end
        ),
        default_local_port=_env_int("DEFAULT_LOCAL_PORT", defaults.default_local_port),
        max_tcp_ports_per_proxy=_env_int(
            "MAX_TCP_PORTS_PER_PROXY", defaults.max_tcp_ports_per_proxy
        ),
        free_recharge_amount_mb=_env_int(
            "FREE_RECHARGE_AMOUNT_MB", defaults.free_recharge_amount_mb
        ),
        default_speed_limit_kbps=_env_int(
            "DEFAULT_SPEED_LIMIT_KBPS", defaults.default_speed_limit_kbps
        ),
        usage_poll_interval_sec=_env_int(
            "USAGE_POLL_INTERVAL_SEC", defaults.usage_poll_interval_sec
        ),
        admin_username=_env_str("ADMIN_USERNAME", defaults.admin_username),
        admin_password=_env_str("ADMIN_PASSWORD", defaults.admin_password),
        max_connections_per_user=_env_int(
            "MAX_CONNECTIONS_PER_USER", defaults.max_connections_per_user
        ),
        demo_bin_base_url_override=_env_str(
            "DEMO_BIN_BASE_URL", defaults.demo_bin_base_url_override
        ),
    )


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)
