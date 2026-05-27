from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ProxyStatus(StrEnum):
    ACTIVE = "active"
    STOPPED_BY_ADMIN = "stopped_by_admin"
    DELETED = "deleted"


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_uid() -> str:
    return f"u_{secrets.token_hex(4)}"


def new_token() -> str:
    return secrets.token_urlsafe(24)


class User(BaseModel):
    uid: str
    created_at: datetime = Field(default_factory=now_utc)
    balance_mb: int = 0
    total_recharged_mb: int = 0


class Proxy(BaseModel):
    id: int
    uid: str
    name: str
    frps_name: str
    token: str
    frps_remote_port: int
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
            if proxy.frps_remote_port == port and proxy.status != ProxyStatus.DELETED:
                return proxy
        return None

    def find_proxy_by_frps_name_unlocked(self, frps_name: str | None) -> Proxy | None:
        if not frps_name:
            return None
        for proxy in self.proxies.values():
            if proxy.frps_name == frps_name and proxy.status != ProxyStatus.DELETED:
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
        return {
            "id": proxy.id,
            "name": proxy.name,
            "token": proxy.token,
            "frps_remote_port": proxy.frps_remote_port,
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
            "created_at": user.created_at.isoformat(),
            "balance_mb": user.balance_mb,
            "total_recharged_mb": user.total_recharged_mb,
            "connection_count": self.active_connection_count_unlocked(user.uid),
        }


store = Store()
