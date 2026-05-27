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
from backend.deps import persist_port_range, port_pool, settings
from backend.models import ProxyStatus, store


router = APIRouter(prefix="/api/admin")


class LoginRequest(BaseModel):
    username: str
    password: str


class UpdateAllocatableRangeRequest(BaseModel):
    start: int
    end: int


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


@router.get("/config", dependencies=[Depends(require_admin)])
async def get_config() -> dict[str, int]:
    start, end = port_pool.get_range()
    return {
        "allocatable_port_range_start": start,
        "allocatable_port_range_end": end,
        "available_port_count": port_pool.available_count(),
    }


@router.put("/config", dependencies=[Depends(require_admin)])
async def update_config(body: UpdateAllocatableRangeRequest) -> dict[str, bool]:
    if body.start < 1 or body.end > 65535:
        raise HTTPException(status_code=400, detail="端口范围必须在 1-65535 之间")
    if body.start > body.end:
        raise HTTPException(status_code=400, detail="起始端口不能大于结束端口")
    async with store.lock:
        currently_allocated = {
            p.frps_remote_port
            for p in store.proxies.values()
            if p.status != ProxyStatus.DELETED
        }
        outside = {
            p for p in currently_allocated
            if p < body.start or p > body.end
        }
        if outside:
            raise HTTPException(
                status_code=400,
                detail=f"新区间不覆盖已分配端口: {sorted(outside)}",
            )
        port_pool.update_range(body.start, body.end, currently_allocated)
    persist_port_range(body.start, body.end)
    return {"ok": True}


@router.get("/proxies", dependencies=[Depends(require_admin)])
async def list_admin_proxies() -> dict[str, list[dict[str, object]]]:
    async with store.lock:
        proxies = [
            store.admin_proxy_to_dto(proxy)
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
        ]
    host = settings.server_public_host
    for p in proxies:
        p["public_url"] = f"http://{host}:{p['frps_remote_port']}/"
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
