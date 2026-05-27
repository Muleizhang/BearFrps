from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from backend.auth import get_or_create_user
from backend.deps import port_pool, settings
from backend.models import Proxy, ProxyStatus, User, new_token, store
from backend.script_renderer import script_renderer


router = APIRouter()


class CreateProxyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    traffic_mb: int = Field(gt=0)
    speed_limit_kbps: int | None = Field(default=None, gt=0)


@router.post("/api/user/init")
async def init_user(user: User = Depends(get_or_create_user)) -> dict[str, object]:
    return {
        "uid": user.uid,
        "balance_mb": user.balance_mb,
        "total_recharged_mb": user.total_recharged_mb,
        "created_at": user.created_at.isoformat(),
    }


@router.post("/api/user/recharge")
async def recharge(user: User = Depends(get_or_create_user)) -> dict[str, int]:
    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        current.balance_mb += settings.free_recharge_amount_mb
        current.total_recharged_mb += settings.free_recharge_amount_mb
        store.add_recharge_unlocked(current.uid, settings.free_recharge_amount_mb)
        return {
            "balance_mb": current.balance_mb,
            "total_recharged_mb": current.total_recharged_mb,
        }


@router.get("/api/proxies")
async def list_proxies(user: User = Depends(get_or_create_user)) -> dict[str, list[dict[str, object]]]:
    async with store.lock:
        proxies = [
            store.proxy_to_dto(proxy)
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
            if proxy.uid == user.uid
        ]
    return {"proxies": proxies}


@router.post("/api/proxies")
async def create_proxy(
    body: CreateProxyRequest,
    response: Response,
    user: User = Depends(get_or_create_user),
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
        dto = store.proxy_to_dto(proxy)

    response.set_cookie("uid", user.uid, httponly=False, samesite="lax", max_age=60 * 60 * 24 * 365)
    return _proxy_scripts_response(proxy, dto)


@router.delete("/api/proxies/{proxy_id}")
async def delete_proxy(proxy_id: int, user: User = Depends(get_or_create_user)) -> dict[str, bool]:
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
async def get_proxy_scripts(proxy_id: int, user: User = Depends(get_or_create_user)) -> dict[str, object]:
    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.uid != user.uid:
            raise HTTPException(status_code=404, detail="proxy not found")
        dto = store.proxy_to_dto(proxy)
    return _proxy_scripts_response(proxy, dto)


def _proxy_scripts_response(proxy: Proxy, dto: dict[str, object]) -> dict[str, object]:
    return {
        "proxy": dto,
        "frpc_config": script_renderer.render_frpc_config(proxy, settings),
        "scripts": script_renderer.render_bundle(proxy, settings),
    }
