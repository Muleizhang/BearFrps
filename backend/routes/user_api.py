from __future__ import annotations

import re
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.auth import (
    USER_SESSION_COOKIE,
    clear_user_session,
    create_user_session,
    register_user_unlocked,
    require_user,
    user_public_dto,
    normalize_username,
    verify_password,
)
from backend.deps import port_pool, settings
from backend.models import Proxy, ProxyStatus, ProxyType, TcpMapping, User, new_token, store
from backend.script_renderer import script_renderer
from backend.user_persistence import save_registered_users_unlocked


def _add_public_url(dto: dict[str, object]) -> dict[str, object]:
    if dto.get("proxy_type") == ProxyType.HTTP.value:
        subdomain = dto.get("subdomain")
        if subdomain:
            port = settings.frps_vhost_http_port
            port_part = "" if port == 80 else f":{port}"
            dto["public_url"] = (
                f"http://{subdomain}.{settings.effective_subdomain_host}{port_part}/"
            )
        else:
            dto["public_url"] = None
        dto["public_urls"] = [dto["public_url"]] if dto["public_url"] else []
    elif dto.get("proxy_type") == ProxyType.XTCP.value:
        dto["public_urls"] = []
        dto["public_url"] = None
    else:
        public_urls = []
        mappings = dto.get("tcp_mappings")
        if isinstance(mappings, list):
            for mapping in mappings:
                if isinstance(mapping, dict) and mapping.get("remote_port") is not None:
                    public_urls.append(
                        f"http://{settings.server_public_host}:{mapping['remote_port']}/"
                    )
        remote_port = dto.get("frps_remote_port")
        if not public_urls and remote_port is not None:
            public_urls.append(f"http://{settings.server_public_host}:{remote_port}/")
        dto["public_urls"] = public_urls
        dto["public_url"] = public_urls[0] if public_urls else None
    return dto


router = APIRouter()
_LOCAL_IP_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_HOST_HEADER_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}(?::[0-9]{1,5})?$")


class TcpPortsRequest(BaseModel):
    mode: Literal["auto", "single", "range"] = "auto"
    count: int | None = Field(default=None, ge=1)
    local_start_port: int | None = Field(default=None, ge=1, le=65535)
    remote_port: int | None = Field(default=None, ge=1, le=65535)
    local_port: int | None = Field(default=None, ge=1, le=65535)
    remote_start_port: int | None = Field(default=None, ge=1, le=65535)
    remote_end_port: int | None = Field(default=None, ge=1, le=65535)


class AdvancedConfigRequest(BaseModel):
    use_encryption: bool = False
    use_compression: bool = False
    bandwidth_limit_mode: str = "server"
    http_user: str | None = Field(default=None, max_length=64)
    http_password: str | None = Field(default=None, max_length=128)
    http_locations: list[str] | None = None
    host_header_rewrite: str | None = Field(default=None, max_length=260)
    keep_tunnel_open: bool | None = None
    fallback_timeout_ms: int | None = None


class CreateProxyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    proxy_type: ProxyType = ProxyType.TCP
    traffic_mb: int = Field(gt=0)
    speed_limit_kbps: int | None = Field(default=None, gt=0)
    local_ip: str | None = None
    local_port: int | None = Field(default=None, ge=1, le=65535)
    subdomain: str | None = None
    tcp_ports: TcpPortsRequest | None = None
    visitor_bind_port: int | None = Field(default=None, ge=1, le=65535)
    advanced_config: AdvancedConfigRequest | None = None


class UserAuthRequest(BaseModel):
    username: str
    password: str


@router.post("/api/user/register")
async def register(
    body: UserAuthRequest,
    response: Response,
    legacy_uid: Annotated[str | None, Cookie(alias="uid")] = None,
) -> dict[str, object]:
    async with store.lock:
        user = register_user_unlocked(body.username, body.password, legacy_uid)
    create_user_session(response, user)
    return user_public_dto(user)


@router.post("/api/user/login")
async def login(body: UserAuthRequest, response: Response) -> dict[str, object]:
    username = normalize_username(body.username)
    async with store.lock:
        user = store.find_user_by_username_unlocked(username)
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")
    create_user_session(response, user)
    return user_public_dto(user)


@router.post("/api/user/logout")
async def logout(
    request: Request,
    response: Response,
) -> dict[str, bool]:
    clear_user_session(response, request.cookies.get(USER_SESSION_COOKIE))
    return {"ok": True}


@router.get("/api/user/me")
async def current_user(user: User = Depends(require_user)) -> dict[str, object]:
    return user_public_dto(user)


@router.post("/api/user/init")
async def init_user(user: User = Depends(require_user)) -> dict[str, object]:
    return user_public_dto(user)


@router.post("/api/user/recharge")
async def recharge(user: User = Depends(require_user)) -> dict[str, int]:
    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        current.balance_mb += settings.free_recharge_amount_mb
        current.total_recharged_mb += settings.free_recharge_amount_mb
        store.add_recharge_unlocked(current.uid, settings.free_recharge_amount_mb)
        save_registered_users_unlocked(store)
        return {
            "balance_mb": current.balance_mb,
            "total_recharged_mb": current.total_recharged_mb,
        }


@router.get("/api/proxies")
async def list_proxies(user: User = Depends(require_user)) -> dict[str, list[dict[str, object]]]:
    async with store.lock:
        proxies = [
            _add_public_url(store.proxy_to_dto(proxy))
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
            if proxy.uid == user.uid
        ]
    return {"proxies": proxies}


@router.post("/api/proxies")
async def create_proxy(
    body: CreateProxyRequest,
    response: Response,
    user: User = Depends(require_user),
) -> dict[str, object]:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    local_ip = _normalize_local_ip(body.local_ip)
    local_port = body.local_port or settings.default_local_port
    subdomain = _normalize_subdomain(body.subdomain) if body.proxy_type == ProxyType.HTTP else None
    visitor_bind_port = body.visitor_bind_port or 9001
    advanced_config = _normalize_advanced_config(body.proxy_type, body.advanced_config)

    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        if body.traffic_mb > current.balance_mb:
            raise HTTPException(status_code=400, detail="余额不足")
        if store.user_has_name_unlocked(current.uid, name):
            raise HTTPException(status_code=400, detail="名称重复")
        if store.active_connection_count_unlocked(current.uid) >= settings.max_connections_per_user:
            raise HTTPException(status_code=400, detail="超过最大连接数")

        remote_port = None
        tcp_mappings: list[TcpMapping] = []
        if body.proxy_type == ProxyType.TCP:
            remote_ports, local_ports = _allocate_tcp_ports(body, local_port)
        elif store.find_proxy_by_subdomain_unlocked(subdomain):
            raise HTTPException(status_code=400, detail="子域名已被占用")

        proxy_id = store.next_proxy_id_unlocked()
        frps_name = f"{current.uid}__{proxy_id}"
        if body.proxy_type == ProxyType.TCP:
            tcp_mappings = [
                TcpMapping(
                    frps_name=_tcp_mapping_name(frps_name, index),
                    remote_port=remote_port_item,
                    local_port=local_port_item,
                    actual_local_port=local_port_item,
                )
                for index, (remote_port_item, local_port_item) in enumerate(
                    zip(remote_ports, local_ports, strict=True)
                )
            ]
            remote_port = tcp_mappings[0].remote_port
            local_port = tcp_mappings[0].local_port
        p2p_secret_key = new_token() if body.proxy_type == ProxyType.XTCP else None
        p2p_fallback_name = (
            f"{frps_name}__fallback" if body.proxy_type == ProxyType.XTCP else None
        )
        proxy = Proxy(
            id=proxy_id,
            uid=current.uid,
            name=name,
            frps_name=frps_name,
            token=new_token(),
            proxy_type=body.proxy_type,
            frps_remote_port=remote_port,
            local_ip=local_ip,
            local_port=local_port,
            subdomain=subdomain,
            tcp_mappings=tcp_mappings,
            p2p_secret_key=p2p_secret_key,
            p2p_fallback_name=p2p_fallback_name,
            visitor_bind_port=visitor_bind_port,
            keep_tunnel_open=advanced_config["keep_tunnel_open"],
            fallback_timeout_ms=advanced_config["fallback_timeout_ms"],
            use_encryption=advanced_config["use_encryption"],
            use_compression=advanced_config["use_compression"],
            bandwidth_limit_mode=advanced_config["bandwidth_limit_mode"],
            http_user=advanced_config["http_user"],
            http_password=advanced_config["http_password"],
            http_locations=advanced_config["http_locations"],
            host_header_rewrite=advanced_config["host_header_rewrite"],
            actual_local_port=local_port,
            speed_limit_kbps=body.speed_limit_kbps or settings.default_speed_limit_kbps,
            traffic_limit_mb=body.traffic_mb,
        )
        store.proxies[proxy.id] = proxy
        if body.proxy_type != ProxyType.XTCP:
            current.balance_mb -= body.traffic_mb
        dto = _add_public_url(store.proxy_to_dto(proxy))
        store.proxies[proxy.id] = proxy
        save_registered_users_unlocked(store)

    return _proxy_scripts_response(proxy, dto)


@router.delete("/api/proxies/{proxy_id}")
async def delete_proxy(proxy_id: int, user: User = Depends(require_user)) -> dict[str, bool]:
    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.uid != user.uid:
            raise HTTPException(status_code=404, detail="proxy not found")
        if proxy.status != ProxyStatus.DELETED:
            proxy.status = ProxyStatus.DELETED
            proxy.is_online = False
            proxy.current_speed_bps = 0
            if proxy.proxy_type == ProxyType.TCP and proxy.frps_remote_port is not None:
                port_pool.release_many([mapping.remote_port for mapping in proxy.tcp_mappings])
    return {"ok": True}


@router.get("/api/proxies/{proxy_id}/scripts")
async def get_proxy_scripts(proxy_id: int, user: User = Depends(require_user)) -> dict[str, object]:
    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.uid != user.uid:
            raise HTTPException(status_code=404, detail="proxy not found")
        dto = _add_public_url(store.proxy_to_dto(proxy))
    return _proxy_scripts_response(proxy, dto)


def _proxy_scripts_response(proxy: Proxy, dto: dict[str, object]) -> dict[str, object]:
    frpc_config = script_renderer.render_frpc_config(proxy, settings)
    return {
        "proxy": dto,
        "frpc_config": frpc_config,
        "frpc_configs": script_renderer.render_frpc_configs(proxy, settings),
        "scripts": script_renderer.render_bundle(proxy, settings),
    }


def _normalize_local_ip(value: str | None) -> str:
    local_ip = (value or "127.0.0.1").strip()
    if not _LOCAL_IP_RE.fullmatch(local_ip):
        raise HTTPException(status_code=400, detail="本地地址格式不合法")
    if ".." in local_ip or local_ip.startswith(".") or local_ip.endswith("."):
        raise HTTPException(status_code=400, detail="本地地址格式不合法")
    return local_ip


def _normalize_subdomain(value: str | None) -> str:
    subdomain = (value or "").strip().lower()
    if not subdomain:
        raise HTTPException(status_code=400, detail="请输入子域名前缀")
    if not _SUBDOMAIN_RE.fullmatch(subdomain):
        raise HTTPException(status_code=400, detail="子域名需为 3-63 位小写字母、数字或连字符")
    return subdomain


def _normalize_advanced_config(
    proxy_type: ProxyType, advanced: AdvancedConfigRequest | None
) -> dict[str, object]:
    config = advanced or AdvancedConfigRequest()
    if config.bandwidth_limit_mode not in ("server", "client"):
        raise HTTPException(status_code=400, detail="限速位置必须是 server 或 client")
    fallback_timeout_ms = (
        config.fallback_timeout_ms if config.fallback_timeout_ms is not None else 1000
    )
    if fallback_timeout_ms < 100 or fallback_timeout_ms > 10000:
        raise HTTPException(status_code=400, detail="fallback 超时需在 100-10000 ms 之间")
    http_user = _clean_optional(config.http_user)
    http_password = _clean_optional(config.http_password)
    if bool(http_user) != bool(http_password):
        raise HTTPException(status_code=400, detail="HTTP 认证用户名和密码需同时填写")

    http_locations: list[str] = []
    host_header_rewrite = None
    if proxy_type == ProxyType.HTTP:
        http_locations = _normalize_http_locations(config.http_locations)
        host_header_rewrite = _normalize_host_header(config.host_header_rewrite)

    return {
        "use_encryption": config.use_encryption,
        "use_compression": config.use_compression,
        "bandwidth_limit_mode": config.bandwidth_limit_mode,
        "http_user": http_user if proxy_type == ProxyType.HTTP else None,
        "http_password": http_password if proxy_type == ProxyType.HTTP else None,
        "http_locations": http_locations if proxy_type == ProxyType.HTTP else [],
        "host_header_rewrite": host_header_rewrite,
        "keep_tunnel_open": (
            config.keep_tunnel_open if config.keep_tunnel_open is not None else True
        ),
        "fallback_timeout_ms": fallback_timeout_ms,
    }


def _clean_optional(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _normalize_http_locations(values: list[str] | None) -> list[str]:
    locations = []
    for item in values or []:
        location = str(item).strip()
        if not location:
            continue
        if not location.startswith("/"):
            raise HTTPException(status_code=400, detail="HTTP 路径必须以 / 开头")
        if any(char.isspace() for char in location):
            raise HTTPException(status_code=400, detail="HTTP 路径不能包含空白字符")
        locations.append(location)
    if len(locations) > 10:
        raise HTTPException(status_code=400, detail="HTTP 路径最多 10 条")
    return locations


def _normalize_host_header(value: str | None) -> str | None:
    host = _clean_optional(value)
    if host is None:
        return None
    if not _HOST_HEADER_RE.fullmatch(host):
        raise HTTPException(status_code=400, detail="Host 改写格式不合法")
    host_part, _, port_part = host.rpartition(":")
    if port_part and host_part:
        port = int(port_part)
        if port < 1 or port > 65535:
            raise HTTPException(status_code=400, detail="Host 改写端口不合法")
        hostname = host_part
    else:
        hostname = host
    if ".." in hostname or hostname.startswith(".") or hostname.endswith("."):
        raise HTTPException(status_code=400, detail="Host 改写格式不合法")
    return host


def _allocate_tcp_ports(
    body: CreateProxyRequest, legacy_local_port: int
) -> tuple[list[int], list[int]]:
    tcp_ports = body.tcp_ports or TcpPortsRequest(
        mode="auto",
        count=1,
        local_start_port=legacy_local_port,
    )
    if tcp_ports.mode == "auto":
        count = tcp_ports.count or 1
        _validate_tcp_port_count(count)
        local_start_port = tcp_ports.local_start_port or legacy_local_port
        local_ports = _local_ports_from_start(local_start_port, count)
        remote_ports = port_pool.allocate_contiguous(count)
        if remote_ports is None:
            raise HTTPException(status_code=400, detail="端口池没有连续可用端口段")
        return remote_ports, local_ports

    if tcp_ports.mode == "single":
        if tcp_ports.remote_port is None:
            raise HTTPException(status_code=400, detail="请输入公网端口")
        if tcp_ports.local_port is None:
            raise HTTPException(status_code=400, detail="请输入本地端口")
        _reserve_requested_remote_ports([tcp_ports.remote_port])
        return [tcp_ports.remote_port], [tcp_ports.local_port]

    if tcp_ports.remote_start_port is None or tcp_ports.remote_end_port is None:
        raise HTTPException(status_code=400, detail="请输入公网端口段")
    if tcp_ports.local_start_port is None:
        raise HTTPException(status_code=400, detail="请输入本地起始端口")
    if tcp_ports.remote_start_port > tcp_ports.remote_end_port:
        raise HTTPException(status_code=400, detail="公网起始端口不能大于结束端口")
    count = tcp_ports.remote_end_port - tcp_ports.remote_start_port + 1
    _validate_tcp_port_count(count)
    remote_ports = list(range(tcp_ports.remote_start_port, tcp_ports.remote_end_port + 1))
    local_ports = _local_ports_from_start(tcp_ports.local_start_port, count)
    _reserve_requested_remote_ports(remote_ports)
    return remote_ports, local_ports


def _validate_tcp_port_count(count: int) -> None:
    if count > settings.max_tcp_ports_per_proxy:
        raise HTTPException(
            status_code=400,
            detail=f"单个 TCP 配置最多 {settings.max_tcp_ports_per_proxy} 个端口",
        )


def _local_ports_from_start(start: int, count: int) -> list[int]:
    if start < 1 or start + count - 1 > 65535:
        raise HTTPException(status_code=400, detail="本地端口段必须在 1-65535 之间")
    return list(range(start, start + count))


def _reserve_requested_remote_ports(ports: list[int]) -> None:
    unavailable = port_pool.reserve_many(ports)
    if unavailable:
        raise HTTPException(
            status_code=400,
            detail=f"公网端口不可用: {sorted(unavailable)}",
        )


def _tcp_mapping_name(base_name: str, index: int) -> str:
    return base_name if index == 0 else f"{base_name}__{index + 1}"
