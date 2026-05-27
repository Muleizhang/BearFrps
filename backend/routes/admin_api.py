from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from backend.auth import (
    ADMIN_SESSION_COOKIE,
    check_admin_credentials,
    clear_admin_session,
    create_admin_session,
    require_admin,
)
from backend.deps import port_pool
from backend.models import ProxyStatus, store


router = APIRouter(prefix="/api/admin")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, bool]:
    if not check_admin_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    create_admin_session(response)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    clear_admin_session(response, request.cookies.get(ADMIN_SESSION_COOKIE))
    return {"ok": True}


@router.get("/proxies", dependencies=[Depends(require_admin)])
async def list_admin_proxies() -> dict[str, list[dict[str, object]]]:
    async with store.lock:
        proxies = [
            store.admin_proxy_to_dto(proxy)
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
        ]
    return {"proxies": proxies}


@router.get("/users", dependencies=[Depends(require_admin)])
async def list_admin_users() -> dict[str, list[dict[str, object]]]:
    async with store.lock:
        users = [store.user_to_dto(user) for user in sorted(store.users.values(), key=lambda u: u.uid)]
    return {"users": users}


@router.post("/proxies/{proxy_id}/stop", dependencies=[Depends(require_admin)])
async def stop_proxy(proxy_id: int) -> dict[str, bool]:
    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.status == ProxyStatus.DELETED:
            raise HTTPException(status_code=404, detail="proxy not found")
        proxy.status = ProxyStatus.STOPPED_BY_ADMIN
        proxy.is_online = False
        proxy.current_speed_bps = 0
    return {"ok": True}


@router.post("/proxies/{proxy_id}/start", dependencies=[Depends(require_admin)])
async def start_proxy(proxy_id: int) -> dict[str, bool]:
    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.status == ProxyStatus.DELETED:
            raise HTTPException(status_code=404, detail="proxy not found")
        user = store.users.get(proxy.uid)
        if user is None or user.balance_mb <= 0:
            raise HTTPException(status_code=400, detail="余额不足")
        owner = store.find_proxy_by_remote_port_unlocked(proxy.frps_remote_port)
        if owner is not None and owner.id != proxy.id:
            raise HTTPException(status_code=400, detail="端口已被占用")
        if port_pool.is_port_available(proxy.frps_remote_port):
            port_pool.reserve(proxy.frps_remote_port)
        proxy.status = ProxyStatus.ACTIVE
    return {"ok": True}


@router.delete("/proxies/{proxy_id}", dependencies=[Depends(require_admin)])
async def delete_proxy(proxy_id: int) -> dict[str, bool]:
    async with store.lock:
        proxy = store.proxies.pop(proxy_id, None)
        if proxy is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        port_pool.release(proxy.frps_remote_port)
    return {"ok": True}
