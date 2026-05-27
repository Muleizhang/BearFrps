from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request

from backend.deps import settings
from backend.models import Proxy, ProxyStatus, store


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
    token = _extract_token(content)
    async with store.lock:
        proxy = store.find_proxy_by_token_unlocked(token)
        if proxy is None:
            proxy = _find_proxy_by_privilege_key_unlocked(content)
        reason = _reject_reason_unlocked(proxy)
        if reason:
            return _reject(reason)

        assert proxy is not None
        content["privilege_key"] = _frps_privilege_key(content.get("timestamp"))
        content.setdefault("metas", {})["token"] = proxy.token
        return _modify(content)


async def _handle_new_proxy(content: dict[str, Any]) -> dict[str, Any]:
    token = _extract_token(content)
    remote_port = content.get("remote_port", content.get("remotePort"))
    proxy_name = content.get("proxy_name", content.get("proxyName"))
    async with store.lock:
        proxy = store.find_proxy_by_token_unlocked(token)
        reason = _reject_reason_unlocked(proxy)
        if reason:
            return _reject(reason)
        assert proxy is not None
        if proxy_name != proxy.frps_name:
            return _reject("proxy name mismatch")
        if remote_port != proxy.frps_remote_port:
            return _reject("remote port mismatch")
        proxy.is_online = True
        proxy.last_seen_at = datetime.now(UTC)

        content["bandwidth_limit"] = f"{proxy.speed_limit_kbps}KB"
        content["bandwidth_limit_mode"] = "server"
        return _modify(content)


async def _handle_close_proxy(content: dict[str, Any]) -> dict[str, Any]:
    proxy_name = content.get("proxy_name", content.get("proxyName"))
    async with store.lock:
        proxy = store.find_proxy_by_frps_name_unlocked(proxy_name)
        if proxy:
            proxy.is_online = False
            proxy.current_speed_bps = 0
            proxy.last_seen_at = datetime.now(UTC)
    return _allow()


async def _handle_ping(content: dict[str, Any]) -> dict[str, Any]:
    token = _extract_token(content)
    async with store.lock:
        proxy = store.find_proxy_by_token_unlocked(token)
        reason = _reject_reason_unlocked(proxy)
        if reason:
            return _reject(reason)
        content["privilege_key"] = _frps_privilege_key(content.get("timestamp"))
        return _modify(content)


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


def _frps_privilege_key(timestamp: Any) -> str:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        ts = 0
    raw = f"{settings.frps_auth_token}{ts}".encode("utf-8")
    return hashlib.md5(raw, usedforsecurity=False).hexdigest()


def _find_proxy_by_privilege_key_unlocked(content: dict[str, Any]) -> Proxy | None:
    privilege_key = content.get("privilege_key")
    timestamp = content.get("timestamp")
    if not privilege_key:
        return None
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return None
    for proxy in store.proxies.values():
        raw = f"{proxy.token}{ts}".encode("utf-8")
        candidate = hashlib.md5(raw, usedforsecurity=False).hexdigest()
        if candidate == privilege_key:
            return proxy
    return None


def _allow() -> dict[str, Any]:
    return {"reject": False, "unchange": True}


def _modify(content: dict[str, Any]) -> dict[str, Any]:
    return {"reject": False, "unchange": False, "content": content}


def _reject(reason: str) -> dict[str, Any]:
    return {"reject": True, "reject_reason": reason, "unchange": True}
