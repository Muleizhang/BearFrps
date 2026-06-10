from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from backend.deps import settings
from backend.models import Proxy, ProxyStatus, ProxyType, User, store


router = APIRouter()


@router.post(settings.plugin_path)
async def frps_plugin(request: Request) -> dict[str, Any]:
    payload = await request.json()
    op = payload.get("op") or request.query_params.get("op")
    content = payload.get("content") or {}

    if op == "Login":
        return await _handle_login(content)
    if op == "NewProxy":
        return await _handle_new_proxy(content)
    if op == "CloseProxy":
        return await _handle_close_proxy(content)
    if op == "Ping":
        return await _handle_ping(content)

    return _allow()


async def _handle_login(content: dict[str, Any]) -> dict[str, Any]:
    async with store.lock:
        user = _find_login_user_unlocked(content)
        reason = _reject_login_reason_unlocked(user)
        if reason:
            return _reject(reason)
        assert user is not None
        _rewrite_login_content(content, user)
        return _modify(content)


async def _handle_new_proxy(content: dict[str, Any]) -> dict[str, Any]:
    remote_port = _as_int(content.get("remote_port", content.get("remotePort")))
    proxy_name = content.get("proxy_name", content.get("proxyName"))
    proxy_type = str(content.get("proxy_type", content.get("proxyType", ""))).lower()
    async with store.lock:
        user, reason = _authenticated_user_unlocked(content)
        if reason:
            return _reject(reason)
        proxy = store.find_proxy_by_frps_name_unlocked(str(proxy_name))
        if proxy is not None and user is not None and proxy.uid != user.uid:
            return _reject("proxy owner mismatch")
        reason = _reject_reason_unlocked(proxy)
        if reason:
            return _reject(reason)
        assert proxy is not None
        if proxy.proxy_type == ProxyType.TCP:
            if proxy_type and proxy_type != proxy.proxy_type.value:
                return _reject("proxy type mismatch")
            mapping = _find_tcp_mapping(proxy, proxy_name)
            if mapping is None:
                return _reject("proxy name mismatch")
            if remote_port != mapping.remote_port:
                return _reject("remote port mismatch")
            mapping.is_online = True
        elif proxy.proxy_type == ProxyType.HTTP:
            if proxy_type and proxy_type != proxy.proxy_type.value:
                return _reject("proxy type mismatch")
            if proxy_name != proxy.frps_name:
                return _reject("proxy name mismatch")
            if _extract_subdomain(content) != proxy.subdomain:
                return _reject("subdomain mismatch")
        else:
            if proxy_name == proxy.frps_name:
                if proxy_type and proxy_type != ProxyType.XTCP.value:
                    return _reject("proxy type mismatch")
                proxy.p2p_xtcp_is_online = True
            elif proxy_name == proxy.p2p_fallback_name:
                if proxy_type and proxy_type != "stcp":
                    return _reject("proxy type mismatch")
                proxy.p2p_fallback_is_online = True
            else:
                return _reject("proxy name mismatch")
        proxy.is_online = True
        proxy.last_seen_at = datetime.now(UTC)

        content["bandwidth_limit"] = f"{proxy.speed_limit_kbps}KB"
        content["bandwidth_limit_mode"] = proxy.bandwidth_limit_mode
        return _modify(content)


async def _handle_close_proxy(content: dict[str, Any]) -> dict[str, Any]:
    proxy_name = content.get("proxy_name", content.get("proxyName"))
    async with store.lock:
        proxy = store.find_proxy_by_frps_name_unlocked(proxy_name)
        if proxy:
            if proxy.proxy_type == ProxyType.TCP:
                mapping = _find_tcp_mapping(proxy, proxy_name)
                if mapping:
                    mapping.is_online = False
                    mapping.current_speed_bps = 0
                proxy.is_online = any(mapping.is_online for mapping in proxy.tcp_mappings)
                proxy.current_speed_bps = sum(
                    mapping.current_speed_bps for mapping in proxy.tcp_mappings
                )
            elif proxy.proxy_type == ProxyType.HTTP:
                proxy.is_online = False
                proxy.current_speed_bps = 0
            else:
                if proxy_name == proxy.frps_name:
                    proxy.p2p_xtcp_is_online = False
                elif proxy_name == proxy.p2p_fallback_name:
                    proxy.p2p_fallback_is_online = False
                proxy.is_online = proxy.p2p_xtcp_is_online or proxy.p2p_fallback_is_online
                if not proxy.p2p_fallback_is_online:
                    proxy.current_speed_bps = 0
            proxy.last_seen_at = datetime.now(UTC)
    return _allow()


async def _handle_ping(content: dict[str, Any]) -> dict[str, Any]:
    async with store.lock:
        user, reason = _authenticated_user_unlocked(content)
        if reason:
            return _reject(reason)
        assert user is not None
        if user.balance_mb <= 0:
            return _reject("insufficient balance")
        if not store.has_active_proxy_unlocked(user.uid):
            return _reject("no active proxy")
        now = datetime.now(UTC)
        for proxy in store.proxies.values():
            if proxy.uid == user.uid and proxy.status == ProxyStatus.ACTIVE:
                proxy.last_seen_at = now
        return _allow()


def _extract_token(content: dict[str, Any]) -> str | None:
    metas = content.get("metas") if isinstance(content.get("metas"), dict) else {}
    if metas.get("token"):
        return str(metas["token"])

    user = content.get("user")
    if isinstance(user, dict):
        user_metas = user.get("metas") if isinstance(user.get("metas"), dict) else {}
        if user_metas.get("token"):
            return str(user_metas["token"])
        if user.get("user"):
            return str(user["user"])

    if content.get("user"):
        return str(content["user"])
    if content.get("token"):
        return str(content["token"])
    return None


def _find_login_user_unlocked(content: dict[str, Any]) -> User | None:
    token = _extract_token(content)
    if token:
        user = _find_user_by_raw_token_unlocked(token)
        if user is not None:
            return user

    user = _find_user_by_privilege_key_unlocked(content)
    if user is not None:
        return user
    return None


def _find_user_by_raw_token_unlocked(token: str) -> User | None:
    for user in store.users.values():
        if hmac.compare_digest(user.frpc_token, token):
            return user

    # Legacy compatibility for configs generated before user-level tokens existed.
    for proxy in store.proxies.values():
        if proxy.status != ProxyStatus.DELETED and hmac.compare_digest(proxy.token, token):
            return store.users.get(proxy.uid)
    return None


def _authenticated_user_unlocked(content: dict[str, Any]) -> tuple[User | None, str | None]:
    uid, token_version = _extract_authenticated_user(content)
    if not uid:
        token = _extract_token(content)
        if token:
            user = _find_user_by_raw_token_unlocked(token)
            if user is not None:
                return user, None
        return None, "invalid token"

    user = store.users.get(uid)
    if user is None:
        return None, "user not found"
    if str(user.frpc_token_version) != str(token_version):
        return None, "token has been rotated"
    return user, None


def _extract_authenticated_user(content: dict[str, Any]) -> tuple[str | None, str | None]:
    user = content.get("user")
    if isinstance(user, dict):
        metas = user.get("metas") if isinstance(user.get("metas"), dict) else {}
        uid = user.get("user") or metas.get("uid")
        token_version = metas.get("token_version")
        return (str(uid) if uid else None, str(token_version) if token_version else None)
    if user:
        return str(user), None
    return None, None


def _extract_subdomain(content: dict[str, Any]) -> str | None:
    if content.get("subdomain"):
        return str(content["subdomain"]).lower()
    custom_domains = content.get("custom_domains", content.get("customDomains"))
    if isinstance(custom_domains, list):
        suffix = "." + settings.effective_subdomain_host.lower()
        for domain in custom_domains:
            value = str(domain).lower()
            if value.endswith(suffix):
                return value[: -len(suffix)]
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_tcp_mapping(proxy: Proxy, frps_name: Any):
    for mapping in proxy.tcp_mappings:
        if mapping.frps_name == frps_name:
            return mapping
    return None


def _reject_reason_unlocked(proxy: Proxy | None) -> str | None:
    if proxy is None:
        return "invalid token"
    user = store.users.get(proxy.uid)
    if user is None:
        return "user not found"
    if proxy.status != ProxyStatus.ACTIVE:
        return "proxy is not active"
    if user.balance_mb <= 0:
        return "insufficient balance"
    if proxy.traffic_used_bytes >= proxy.traffic_limit_mb * 1024 * 1024:
        return "traffic limit exceeded"
    return None


def _reject_login_reason_unlocked(user: User | None) -> str | None:
    if user is None:
        return "invalid token"
    if user.balance_mb <= 0:
        return "insufficient balance"
    if not store.has_active_proxy_unlocked(user.uid):
        return "no active proxy"
    return None


def _find_user_by_privilege_key_unlocked(content: dict[str, Any]) -> User | None:
    privilege_key = content.get("privilege_key")
    timestamp = content.get("timestamp")
    if not privilege_key:
        return None
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return None
    for user in store.users.values():
        if hmac.compare_digest(_auth_key(user.frpc_token, ts), str(privilege_key)):
            return user

    # Legacy compatibility for per-proxy tokens from older generated configs.
    for proxy in store.proxies.values():
        if proxy.status == ProxyStatus.DELETED:
            continue
        if hmac.compare_digest(_auth_key(proxy.token, ts), str(privilege_key)):
            return store.users.get(proxy.uid)
    return None


def _rewrite_login_content(content: dict[str, Any], user: User) -> None:
    content["user"] = user.uid
    content["metas"] = {
        "uid": user.uid,
        "token_version": str(user.frpc_token_version),
    }


def _auth_key(token: str, timestamp: int) -> str:
    raw = f"{token}{timestamp}".encode("utf-8")
    return hashlib.md5(raw, usedforsecurity=False).hexdigest()


def _allow() -> dict[str, Any]:
    return {"reject": False, "unchange": True}


def _modify(content: dict[str, Any]) -> dict[str, Any]:
    return {"reject": False, "unchange": False, "content": content}


def _reject(reason: str) -> dict[str, Any]:
    return {"reject": True, "reject_reason": reason, "unchange": True}
