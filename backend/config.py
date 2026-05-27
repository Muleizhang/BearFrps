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

    plugin_path: str = "/frps-plugin"
    remote_port_range_start: int = 50000
    remote_port_range_end: int = 50100
    default_local_port: int = 527

    free_recharge_amount_mb: int = 100
    default_speed_limit_kbps: int = 1024
    usage_poll_interval_sec: int = 2

    admin_username: str = "admin"
    admin_password: str = "changeme"
    max_connections_per_user: int = 3

    @property
    def frp_version_without_v(self) -> str:
        return self.frps_version[1:] if self.frps_version.startswith("v") else self.frps_version

    @property
    def demo_bin_base_url(self) -> str:
        return f"http://{self.server_public_host}:{self.backend_port}/static/demo-server-bin"

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
        plugin_path=_env_str("PLUGIN_PATH", defaults.plugin_path),
        remote_port_range_start=_env_int(
            "REMOTE_PORT_RANGE_START", defaults.remote_port_range_start
        ),
        remote_port_range_end=_env_int("REMOTE_PORT_RANGE_END", defaults.remote_port_range_end),
        default_local_port=_env_int("DEFAULT_LOCAL_PORT", defaults.default_local_port),
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
    )


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)
