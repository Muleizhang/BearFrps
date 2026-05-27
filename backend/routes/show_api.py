from __future__ import annotations

from fastapi import APIRouter

from backend.deps import settings
from backend.models import ProxyStatus, store


router = APIRouter()


@router.get("/api/show/online")
async def show_online() -> dict[str, list[dict[str, object]]]:
    async with store.lock:
        proxies = [
            {
                "id": proxy.id,
                "name": proxy.name,
                "remote_port": proxy.frps_remote_port,
                "public_url": f"http://{settings.server_public_host}:{proxy.frps_remote_port}/",
            }
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
            if proxy.status == ProxyStatus.ACTIVE and proxy.is_online
        ]
    return {"proxies": proxies}
