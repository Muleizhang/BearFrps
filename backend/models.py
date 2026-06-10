"""@file backend/models.py
@brief 定义用户、代理、TCP 映射、充值记录和进程内 Store。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：pydantic、asyncio.Lock、标准库 datetime/secrets。
  修改记录：2026-06-10，补充 Doxygen 风格文件头、数据成员和仓库约束说明。
  User.frpc_token 是用户级 frpc 元数据令牌，轮换后旧配置应被插件拒绝。
  Proxy.token 保留为历史兼容字段，新配置优先使用用户级 frpc_token。
  Proxy.frps_name 是实际传给 frps 的内部代理名，避免用户自定义名称冲突。
  TcpMapping 保存单个本地端口到远程端口的映射，多端口 TCP 代理由列表表达。
  traffic_used_bytes/current_speed_bps 由轮询器更新，不由前端直接写入。

  Store 方法名带 unlocked 表示调用者必须已经持有 store.lock。
  Store 是课堂演示用进程内仓库，不替代生产数据库。
  删除代理使用状态标记，便于保留审计和避免展示页读取已删除对象。
  DTO 方法负责隐藏内部字段，只输出前端需要的安全信息。

  ProxyStatus.ACTIVE 表示代理可被 frps 插件接受。
  ProxyStatus.STOPPED_BY_ADMIN 表示代理被流量、余额或管理员策略停用。
  ProxyStatus.DELETED 表示逻辑删除，列表接口默认不再展示给普通用户。
  ProxyType.TCP 用于公网端口转发，必须占用端口池 remotePort。
  ProxyType.HTTP 用于虚拟主机或子域名访问，不占用 TCP 端口池。
  ProxyType.STCP 和 ProxyType.XTCP 用于点对点场景，需要 visitor 配置。
  TcpMapping.local_port 是用户本机端口，用户可以按实际服务修改。
  TcpMapping.remote_port 是平台分配或校验的公网端口，不允许用户随意改动。
  User.password_hash 使用 PBKDF2 结果，不保存明文密码。
  User.frpc_token_version 用于令牌轮换后拒绝旧 frpc 心跳。
  User.balance_mb 是创建代理时扣减的课堂演示流量余额。
  Proxy.traffic_limit_mb 是单个代理分配的流量额度。
  Proxy.traffic_used_bytes 是 frps 轮询得到的累计用量。
  Proxy.current_speed_bps 是轮询器根据差值计算的瞬时速度。
  Proxy.last_seen_at 在插件 CloseProxy 和轮询器状态更新时维护。
  Proxy.public_url/public_urls 只用于前端展示，不参与 frps 鉴权。
  Proxy.advanced_config 相关字段映射到 frpc transport、HTTP header 或 P2P 配置。

  proxy_to_dto 面向普通用户，包含脚本生成和状态展示需要的字段。
  admin_proxy_to_dto 面向管理员，额外包含 uid 等管理字段。
  user_to_dto 面向管理端和用户端，隐藏 password_hash。
  _tcp_mapping_to_dto 统一多端口映射字段命名，避免前端重复转换。

  Store.lock 是整个内存仓库的唯一互斥锁。
  路由、插件和轮询器都必须在修改 users/proxies/recharge_logs 前进入该锁。
  next_proxy_id_unlocked 只在锁内递增，保证同一进程内代理 id 不重复。
  sync_user_proxy_tokens_unlocked 用于令牌轮换后同步旧代理兼容字段。
  find_proxy_by_frps_name_unlocked 统一解析 TCP 多映射、P2P fallback 和普通代理名。

  数据模型能对应需求规格中的 User、Proxy、RechargeLog。
  每个代理都有 uid，满足多租户隔离要求。
  每个代理都有 status，满足管理员停用和删除要求。
  每个 TCP 映射都有 local_port 和 remote_port，满足端口映射展示要求。
  每个用户都有 balance_mb，满足流量额度扣减要求。
  每个用户都有 frpc_token，满足多用户令牌隔离要求。
  每个代理都有 created_at，满足审计和展示要求。
  Store.reset 支持测试隔离，满足自动化测试要求。
  DTO 函数集中处理输出，满足敏感字段隐藏要求。
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

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
    frpc_token: str = Field(default_factory=new_token)
    frpc_token_version: int = 1
    frpc_token_rotated_at: datetime = Field(default_factory=now_utc)
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
    use_encryption: bool = False
    use_compression: bool = False
    bandwidth_limit_mode: Literal["server", "client"] = "server"
    http_user: str | None = None
    http_password: str | None = None
    http_locations: list[str] = Field(default_factory=list)
    host_header_rewrite: str | None = None
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
            user = self.users.get(proxy.uid)
            current_token = user.frpc_token if user else proxy.token
            if current_token == token and proxy.status != ProxyStatus.DELETED:
                return proxy
        return None

    def user_frpc_token_unlocked(self, uid: str) -> str | None:
        user = self.users.get(uid)
        return user.frpc_token if user else None

    def sync_user_proxy_tokens_unlocked(self, uid: str) -> None:
        token = self.user_frpc_token_unlocked(uid)
        if not token:
            return
        for proxy in self.proxies.values():
            if proxy.uid == uid and proxy.status != ProxyStatus.DELETED:
                proxy.token = token

    def has_active_proxy_unlocked(self, uid: str) -> bool:
        return any(
            proxy.uid == uid and proxy.status == ProxyStatus.ACTIVE
            for proxy in self.proxies.values()
        )

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
        user = self.users.get(proxy.uid)
        token = user.frpc_token if user else proxy.token
        return {
            "id": proxy.id,
            "name": proxy.name,
            "frps_name": proxy.frps_name,
            "token": token,
            "token_version": user.frpc_token_version if user else None,
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
            "use_encryption": proxy.use_encryption,
            "use_compression": proxy.use_compression,
            "bandwidth_limit_mode": proxy.bandwidth_limit_mode,
            "http_user": proxy.http_user,
            "http_password": proxy.http_password,
            "http_locations": proxy.http_locations,
            "host_header_rewrite": proxy.host_header_rewrite,
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
            "frpc_token_version": user.frpc_token_version,
            "frpc_token_rotated_at": user.frpc_token_rotated_at.isoformat(),
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
