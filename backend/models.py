from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class ProxyStatus(StrEnum):
    ACTIVE = "active"
    STOPPED_BY_ADMIN = "stopped_by_admin"
    DELETED = "deleted"


class ProxyType(StrEnum):
    TCP = "tcp"
    HTTP = "http"
    XTCP = "xtcp"


class TcpMapping(BaseModel):
    frps_name: str
    remote_port: int
    local_port: int
    is_online: bool = False
    actual_local_port: int | None = None
    current_speed_bps: int = 0
    last_frps_total_bytes: int | None = None


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_uid() -> str:
    return f"u_{secrets.token_hex(4)}"


def new_token() -> str:
    return secrets.token_urlsafe(24)


class User(BaseModel):
    uid: str
    username: str | None = None
    password_hash: str | None = None
    created_at: datetime = Field(default_factory=now_utc)
    balance_mb: int = 0
    total_recharged_mb: int = 0


class Proxy(BaseModel):
    id: int
    uid: str
    name: str
    frps_name: str
    token: str
    proxy_type: ProxyType = ProxyType.TCP
    frps_remote_port: int | None = None
    local_ip: str = "127.0.0.1"
    local_port: int = 9527
    subdomain: str | None = None
    tcp_mappings: list[TcpMapping] = Field(default_factory=list)
    p2p_secret_key: str | None = None
    p2p_fallback_name: str | None = None
    visitor_bind_addr: str = "127.0.0.1"
    visitor_bind_port: int = 9001
    keep_tunnel_open: bool = True
    fallback_timeout_ms: int = 1000
    p2p_xtcp_is_online: bool = False
    p2p_fallback_is_online: bool = False
    actual_local_port: int | None = None
    status: ProxyStatus = ProxyStatus.ACTIVE
    is_online: bool = False
    speed_limit_kbps: int
    traffic_limit_mb: int
    traffic_used_bytes: int = 0
    current_speed_bps: int = 0
    created_at: datetime = Field(default_factory=now_utc)
    last_seen_at: datetime | None = None
    last_frps_total_bytes: int | None = None

    @model_validator(mode="after")
    def normalize_tcp_mappings(self) -> Proxy:
        if self.proxy_type != ProxyType.TCP:
            self.tcp_mappings = []
            return self
        if not self.tcp_mappings and self.frps_remote_port is not None:
            self.tcp_mappings = [
                TcpMapping(
                    frps_name=self.frps_name,
                    remote_port=self.frps_remote_port,
                    local_port=self.local_port,
                    is_online=self.is_online,
                    actual_local_port=self.actual_local_port,
                    current_speed_bps=self.current_speed_bps,
                    last_frps_total_bytes=self.last_frps_total_bytes,
                )
            ]
        if self.tcp_mappings:
            first = self.tcp_mappings[0]
            self.frps_remote_port = first.remote_port
            self.local_port = first.local_port
            self.actual_local_port = first.actual_local_port
        return self


class RechargeLog(BaseModel):
    id: int
    uid: str
    amount_mb: int
    created_at: datetime = Field(default_factory=now_utc)


class Store:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.users: dict[str, User] = {}
        self.proxies: dict[int, Proxy] = {}
        self.proxy_id_counter = 0
        self.recharge_id_counter = 0
        self.recharge_logs: list[RechargeLog] = []

    def reset(self) -> None:
        self.users.clear()
        self.proxies.clear()
        self.proxy_id_counter = 0
        self.recharge_id_counter = 0
        self.recharge_logs.clear()

    def ensure_user_unlocked(self, uid: str | None = None) -> User:
        if uid and uid in self.users:
            return self.users[uid]
        generated_uid = uid or new_uid()
        while generated_uid in self.users:
            generated_uid = new_uid()
        user = User(uid=generated_uid)
        self.users[user.uid] = user
        return user

    def find_user_by_username_unlocked(self, username: str) -> User | None:
        for user in self.users.values():
            if user.username == username:
                return user
        return None

    def add_recharge_unlocked(self, uid: str, amount_mb: int) -> RechargeLog:
        self.recharge_id_counter += 1
        log = RechargeLog(id=self.recharge_id_counter, uid=uid, amount_mb=amount_mb)
        self.recharge_logs.append(log)
        return log

    def next_proxy_id_unlocked(self) -> int:
        self.proxy_id_counter += 1
        return self.proxy_id_counter

    def find_proxy_by_token_unlocked(self, token: str | None) -> Proxy | None:
        if not token:
            return None
        for proxy in self.proxies.values():
            if proxy.token == token and proxy.status != ProxyStatus.DELETED:
                return proxy
        return None

    def find_proxy_by_remote_port_unlocked(self, port: int | None) -> Proxy | None:
        if port is None:
            return None
        for proxy in self.proxies.values():
            if (
                proxy.proxy_type == ProxyType.TCP
                and any(mapping.remote_port == port for mapping in proxy.tcp_mappings)
                and proxy.status != ProxyStatus.DELETED
            ):
                return proxy
        return None

    def find_proxy_by_subdomain_unlocked(
        self, subdomain: str | None, exclude_id: int | None = None
    ) -> Proxy | None:
        if not subdomain:
            return None
        for proxy in self.proxies.values():
            if (
                proxy.proxy_type == ProxyType.HTTP
                and proxy.subdomain == subdomain
                and proxy.status != ProxyStatus.DELETED
                and proxy.id != exclude_id
            ):
                return proxy
        return None

    def find_proxy_by_frps_name_unlocked(self, frps_name: str | None) -> Proxy | None:
        if not frps_name:
            return None
        for proxy in self.proxies.values():
            if proxy.status == ProxyStatus.DELETED:
                continue
            if proxy.frps_name == frps_name:
                return proxy
            if (
                proxy.proxy_type == ProxyType.XTCP
                and proxy.p2p_fallback_name == frps_name
            ):
                return proxy
            if (
                proxy.proxy_type == ProxyType.TCP
                and any(mapping.frps_name == frps_name for mapping in proxy.tcp_mappings)
            ):
                return proxy
        return None

    def active_connection_count_unlocked(self, uid: str) -> int:
        return sum(
            1
            for proxy in self.proxies.values()
            if proxy.uid == uid and proxy.status != ProxyStatus.DELETED
        )

    def user_has_name_unlocked(self, uid: str, name: str, exclude_id: int | None = None) -> bool:
        return any(
            proxy.uid == uid
            and proxy.name == name
            and proxy.status != ProxyStatus.DELETED
            and proxy.id != exclude_id
            for proxy in self.proxies.values()
        )

    def proxy_to_dto(self, proxy: Proxy) -> dict[str, Any]:
        tcp_mappings = [_tcp_mapping_to_dto(mapping) for mapping in proxy.tcp_mappings]
        return {
            "id": proxy.id,
            "name": proxy.name,
            "frps_name": proxy.frps_name,
            "token": proxy.token,
            "proxy_type": proxy.proxy_type.value,
            "frps_remote_port": proxy.frps_remote_port,
            "local_ip": proxy.local_ip,
            "local_port": proxy.local_port,
            "subdomain": proxy.subdomain,
            "tcp_mappings": tcp_mappings,
            "p2p_secret_key": proxy.p2p_secret_key,
            "p2p_fallback_name": proxy.p2p_fallback_name,
            "visitor_bind_addr": proxy.visitor_bind_addr,
            "visitor_bind_port": proxy.visitor_bind_port,
            "visitor_endpoint": f"{proxy.visitor_bind_addr}:{proxy.visitor_bind_port}",
            "keep_tunnel_open": proxy.keep_tunnel_open,
            "fallback_timeout_ms": proxy.fallback_timeout_ms,
            "p2p_xtcp_is_online": proxy.p2p_xtcp_is_online,
            "p2p_fallback_is_online": proxy.p2p_fallback_is_online,
            "actual_local_port": proxy.actual_local_port,
            "status": proxy.status.value,
            "is_online": proxy.is_online,
            "speed_limit_kbps": proxy.speed_limit_kbps,
            "traffic_limit_mb": proxy.traffic_limit_mb,
            "traffic_used_bytes": proxy.traffic_used_bytes,
            "current_speed_bps": proxy.current_speed_bps,
            "created_at": proxy.created_at.isoformat(),
            "last_seen_at": proxy.last_seen_at.isoformat() if proxy.last_seen_at else None,
        }

    def admin_proxy_to_dto(self, proxy: Proxy) -> dict[str, Any]:
        dto = self.proxy_to_dto(proxy)
        dto["uid"] = proxy.uid
        return dto

    def user_to_dto(self, user: User) -> dict[str, Any]:
        return {
            "uid": user.uid,
            "username": user.username,
            "created_at": user.created_at.isoformat(),
            "balance_mb": user.balance_mb,
            "total_recharged_mb": user.total_recharged_mb,
            "connection_count": self.active_connection_count_unlocked(user.uid),
        }


def _tcp_mapping_to_dto(mapping: TcpMapping) -> dict[str, Any]:
    return {
        "frps_name": mapping.frps_name,
        "remote_port": mapping.remote_port,
        "local_port": mapping.local_port,
        "is_online": mapping.is_online,
        "actual_local_port": mapping.actual_local_port,
        "current_speed_bps": mapping.current_speed_bps,
    }


store = Store()
