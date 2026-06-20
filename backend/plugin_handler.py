"""@file backend/plugin_handler.py
@brief 处理 frps Login、NewProxy、CloseProxy、Ping 回调并执行多租户鉴权。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：FastAPI APIRouter、backend.models、backend.deps.settings。
  修改记录：2026-06-10，补充 Doxygen 风格文件头、鉴权规则和兼容逻辑说明。
  Login 使用用户级 metadatas.token 找到 User，并重写 content.user 与 metas。
  NewProxy 按代理类型校验 remotePort、subdomain、serverName 或 fallback 代理名。
  Ping 校验 uid 和 token_version，用户轮换令牌后旧 frpc 会被拒绝。
  CloseProxy 只更新在线状态和 last_seen_at，不删除代理记录。
  旧版本配置可能仍使用 per-proxy token，本模块保留 find_proxy_by_token fallback。
  frp 官方 v0.58.1 要求 frpc auth.token 与 frps auth.token 匹配，因此租户令牌放在 metadatas.token。
  插件返回 reject reason 会给 frps 日志使用，避免暴露敏感 token。
  会修改代理在线状态、最后上线时间，以及 Login content 中的用户和 metas。
  frps_plugin 是唯一公开插件入口，op 可来自 JSON payload 或查询参数。
  未识别的 op 默认 allow，避免 frps 新增事件导致课堂演示连接全部失败。
  _handle_login 只负责认证用户和改写 content，不绑定具体代理端口。
  _handle_new_proxy 负责把 frps 准备创建的代理和平台记录逐项比对。
  _handle_close_proxy 是幂等操作，重复 close 不应改变代理归属和配额。
  _handle_ping 是轮换令牌后的关键防线，旧配置会在下一次 ping 被拒绝。

  privilege_key 是 frp token 认证字段，使用 shared auth.token 计算。
  metadatas.token 是 BearFrps 用户级令牌，作为租户身份。
  metadatas.uid 是前端用户 uid，必须和令牌推导出的用户一致。
  metas.token_version 是 Login 后写入的版本号，用于后续 Ping 校验。
  remotePort 只对 TCP 代理有意义，XTCP 的 stcp fallback 通过 serverName 匹配。
  subdomain/customDomains 只对 HTTP 代理有意义。

  用户不存在或令牌错误，拒绝 Login。
  用户余额小于等于 0，拒绝 Login。
  用户没有 active 代理，拒绝 Login。
  代理被管理员停用或删除，拒绝 NewProxy。
  TCP remotePort 与平台记录不一致，拒绝 NewProxy。
  HTTP subdomain 与平台记录不一致，拒绝 NewProxy。
  Ping 中 uid 不匹配或 token_version 过期，拒绝继续连接。

  _find_user_by_raw_token_unlocked 优先查用户级令牌。
  历史配置的 per-proxy token 仍可映射到 proxy.uid。
  _find_user_by_privilege_key_unlocked 兼容旧脚本把代理 token 放入 auth.token 的情况。
  兼容路径只用于平滑升级，新脚本应使用 metadatas.token。

  插件只相信后端 Store 中的代理记录，不相信 frpc 自报的代理名或端口。
  reject reason 不包含 token 明文。
  Login 改写 user 字段后，后续事件可以用 uid 做快速归属校验。
  token_version 以字符串写入 metas，是为了兼容 frp 元数据字段的字符串表达。
"""

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
    if proxy.traffic_used_bytes >= proxy.traffic_limit_mb * 1024 * 1024:
        return "traffic limit exceeded"
    return None


def _reject_login_reason_unlocked(user: User | None) -> str | None:
    if user is None:
        return "invalid token"
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
