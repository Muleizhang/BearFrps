from __future__ import annotations

from typing import Annotated

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
from backend.models import Proxy, ProxyStatus, User, new_token, store
from backend.script_renderer import script_renderer
from backend.user_persistence import save_registered_users_unlocked


def _add_public_url(dto: dict[str, object]) -> dict[str, object]:
    dto["public_url"] = f"http://{settings.server_public_host}:{dto['frps_remote_port']}/"
    return dto


router = APIRouter()


class CreateProxyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    traffic_mb: int = Field(gt=0)
    speed_limit_kbps: int | None = Field(default=None, gt=0)


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

    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        if body.traffic_mb > current.balance_mb:
            raise HTTPException(status_code=400, detail="余额不足")
        if store.user_has_name_unlocked(current.uid, name):
            raise HTTPException(status_code=400, detail="名称重复")
        if store.active_connection_count_unlocked(current.uid) >= settings.max_connections_per_user:
            raise HTTPException(status_code=400, detail="超过最大连接数")

        remote_port = port_pool.allocate()
        if remote_port is None:
            raise HTTPException(status_code=400, detail="端口池满")

        proxy_id = store.next_proxy_id_unlocked()
        proxy = Proxy(
            id=proxy_id,
            uid=current.uid,
            name=name,
            frps_name=f"{current.uid}__{proxy_id}",
            token=new_token(),
            frps_remote_port=remote_port,
            speed_limit_kbps=body.speed_limit_kbps or settings.default_speed_limit_kbps,
            traffic_limit_mb=body.traffic_mb,
        )
        store.proxies[proxy.id] = proxy
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
            port_pool.release(proxy.frps_remote_port)
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
    return {
        "proxy": dto,
        "frpc_config": script_renderer.render_frpc_config(proxy, settings),
        "scripts": script_renderer.render_bundle(proxy, settings),
    }
