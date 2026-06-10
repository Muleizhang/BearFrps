from __future__ import annotations

from fastapi import APIRouter

from backend.deps import settings
from backend.models import ProxyStatus, ProxyType, store


router = APIRouter()


@router.get("/api/show/online")
async def show_online() -> dict[str, list[dict[str, object]]]:
    async with store.lock:
        proxies = [
            {
                "id": proxy.id,
                "name": proxy.name,
                "proxy_type": proxy.proxy_type.value,
                "remote_port": proxy.frps_remote_port,
                "remote_ports": [mapping.remote_port for mapping in proxy.tcp_mappings],
                "tcp_mappings": [
                    {
                        "frps_name": mapping.frps_name,
                        "remote_port": mapping.remote_port,
                        "local_port": mapping.local_port,
                        "is_online": mapping.is_online,
                        "actual_local_port": mapping.actual_local_port,
                    }
                    for mapping in proxy.tcp_mappings
                ],
                "public_url": _public_url(proxy),
                "public_urls": _public_urls(proxy),
            }
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
            if proxy.status == ProxyStatus.ACTIVE and proxy.is_online
        ]
    return {"proxies": proxies}


def _public_url(proxy) -> str | None:
    urls = _public_urls(proxy)
    return urls[0] if urls else None


def _public_urls(proxy) -> list[str]:
    if proxy.proxy_type == ProxyType.HTTP:
        if not proxy.subdomain:
            return []
        port = settings.frps_vhost_http_port
        port_part = "" if port == 80 else f":{port}"
        return [f"http://{proxy.subdomain}.{settings.effective_subdomain_host}{port_part}/"]
    return [
        f"http://{settings.server_public_host}:{mapping.remote_port}/"
        for mapping in proxy.tcp_mappings
    ]
