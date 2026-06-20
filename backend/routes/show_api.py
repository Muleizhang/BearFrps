"""@file backend/routes/show_api.py
@brief 为展示页输出当前在线且可访问的用户代理列表。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：FastAPI、backend.deps.settings、backend.models。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和展示过滤规则。
  只展示 status=active 且 is_online=true 的代理。
  不输出用户 token、frps 内部 token、管理员字段或密码信息。
  TCP 使用 server_public_host 和 remotePort 拼接访问地址。
  HTTP 代理优先使用 public_url/public_urls，支持 subdomain 展示。
  展示接口无登录要求，因此输出字段必须保持最小化。
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.deps import settings
from backend.models import ProxyStatus, ProxyType, store


router = APIRouter()


@router.get("/api/show/online")
async def show_online() -> dict[str, list[dict[str, object]]]:
    """@brief 返回展示页可公开显示的在线代理列表。
    @return proxies 数组，只包含展示所需字段和访问地址。
    @note 展示页无鉴权，不能返回 uid、token、密码或管理员字段。
    """

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
                "visitor_endpoint": (
                    f"{proxy.visitor_bind_addr}:{proxy.visitor_bind_port}"
                    if proxy.proxy_type == ProxyType.XTCP
                    else None
                ),
            }
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
            if proxy.status == ProxyStatus.ACTIVE and proxy.is_online
        ]
    return {"proxies": proxies}


def _public_url(proxy) -> str | None:
    """@brief 返回代理的第一个展示访问地址。
    @param proxy 代理模型。
    @return 可点击公网 URL；XTCP 或无地址时返回 None。
    """

    urls = _public_urls(proxy)
    return urls[0] if urls else None


def _public_urls(proxy) -> list[str]:
    """@brief 根据代理类型生成展示页访问地址列表。
    @param proxy 代理模型。
    @return HTTP 子域名 URL 或 TCP 端口 URL 列表。
    @note XTCP 需要本地 visitor，因此展示页不生成公网 URL。
    """

    if proxy.proxy_type == ProxyType.HTTP:
        if not proxy.subdomain:
            return []
        port = settings.public_vhost_http_port
        port_part = "" if port == 80 else f":{port}"
        return [f"http://{proxy.subdomain}.{settings.effective_subdomain_host}{port_part}/"]
    if proxy.proxy_type != ProxyType.TCP:
        return []
    return [
        f"http://{settings.server_public_host}:{mapping.remote_port}/"
        for mapping in proxy.tcp_mappings
    ]
