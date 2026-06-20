"""@file backend/routes/admin_api.py
@brief 提供管理员登录、端口池配置、代理管理和用户列表接口。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：FastAPI、backend.auth、backend.deps、backend.models。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和管理操作约束。
  /api/admin/login 和 /logout 管理管理员 session。
  /api/admin/config 读取或更新可分配公网端口范围。
  /api/admin/proxies 返回全量代理 DTO，并允许停用、恢复和删除。
  /api/admin/users 返回注册用户和连接数量。
  缩小端口池前必须检查 active TCP 代理是否仍在新范围内。
  HTTP/XTCP 不占用平台 TCP 端口池，端口范围检查只针对 TCP remotePort。
  管理员删除代理会释放端口，停用代理不释放端口，避免用户配置被其他人抢占。
"""

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
from backend.models import ProxyStatus, ProxyType, store


router = APIRouter(prefix="/api/admin")


class LoginRequest(BaseModel):
    """@brief 管理员登录请求体。"""

    username: str
    password: str


class UpdateAllocatableRangeRequest(BaseModel):
    """@brief 管理员更新公网 TCP 端口池范围的请求体。"""

    start: int
    end: int


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, bool]:
    """@brief 校验管理员账号并写入管理端 session。
    @param body 管理员用户名和密码。
    @param response FastAPI 响应对象，用于写入管理员 cookie。
    @return ok=true 表示登录成功。
    @throws HTTPException 凭据错误时返回 401。
    """

    if not check_admin_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    create_admin_session(response)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict[str, bool]:
    """@brief 清除管理端 session。
    @param request FastAPI 请求对象，用于读取管理员 cookie。
    @param response FastAPI 响应对象，用于删除管理员 cookie。
    @return ok=true 表示退出完成。
    """

    clear_admin_session(response, request.cookies.get(ADMIN_SESSION_COOKIE))
    return {"ok": True}


@router.get("/config", dependencies=[Depends(require_admin)])
async def get_config() -> dict[str, int]:
    """@brief 返回当前端口池配置和剩余可用数量。
    @return 端口池起止范围和 available_port_count。
    """

    start, end = port_pool.get_range()
    return {
        "allocatable_port_range_start": start,
        "allocatable_port_range_end": end,
        "available_port_count": port_pool.available_count(),
    }


@router.put("/config", dependencies=[Depends(require_admin)])
async def update_config(body: UpdateAllocatableRangeRequest) -> dict[str, bool]:
    """@brief 更新可分配公网 TCP 端口范围。
    @param body 新的闭区间 start/end。
    @return ok=true 表示配置已持久化。
    @throws HTTPException 范围非法或不能覆盖已分配端口时返回 400。
    @note 缩小范围前会检查所有未删除 TCP 映射，避免已发脚本对应端口失效。
    """

    if body.start < 1 or body.end > 65535:
        raise HTTPException(status_code=400, detail="端口范围必须在 1-65535 之间")
    if body.start > body.end:
        raise HTTPException(status_code=400, detail="起始端口不能大于结束端口")
    async with store.lock:
        currently_allocated = {
            mapping.remote_port
            for p in store.proxies.values()
            for mapping in p.tcp_mappings
            if (
                p.proxy_type == ProxyType.TCP
                and p.status != ProxyStatus.DELETED
            )
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
    """@brief 返回管理员视角的全量代理列表。
    @return proxies 数组，包含用户归属、状态和展示访问地址。
    @note XTCP 只能通过 visitor 访问，因此不生成 public_url。
    """

    async with store.lock:
        proxies = [
            store.admin_proxy_to_dto(proxy)
            for proxy in sorted(store.proxies.values(), key=lambda p: p.id)
        ]
    host = settings.server_public_host
    for p in proxies:
        if p.get("proxy_type") == ProxyType.HTTP.value:
            port = settings.public_vhost_http_port
            port_part = "" if port == 80 else f":{port}"
            p["public_url"] = (
                f"http://{p['subdomain']}.{settings.effective_subdomain_host}{port_part}/"
                if p.get("subdomain")
                else None
            )
            p["public_urls"] = [p["public_url"]] if p["public_url"] else []
        elif p.get("proxy_type") == ProxyType.TCP.value:
            public_urls = [
                f"http://{host}:{mapping['remote_port']}/"
                for mapping in p.get("tcp_mappings", [])
                if isinstance(mapping, dict) and mapping.get("remote_port") is not None
            ]
            if not public_urls and p.get("frps_remote_port") is not None:
                public_urls.append(f"http://{host}:{p['frps_remote_port']}/")
            p["public_urls"] = public_urls
            p["public_url"] = public_urls[0] if public_urls else None
        else:
            p["public_urls"] = []
            p["public_url"] = None
    return {"proxies": proxies}


@router.get("/users", dependencies=[Depends(require_admin)])
async def list_admin_users() -> dict[str, list[dict[str, object]]]:
    """@brief 返回管理员视角的注册用户列表。
    @return users 数组，隐藏 password_hash。
    """

    async with store.lock:
        users = [store.user_to_dto(user) for user in sorted(store.users.values(), key=lambda u: u.uid)]
    return {"users": users}


@router.post("/proxies/{proxy_id}/stop", dependencies=[Depends(require_admin)])
async def stop_proxy(proxy_id: int) -> dict[str, bool]:
    """@brief 管理员停用指定代理。
    @param proxy_id 代理 ID。
    @return ok=true 表示状态已切换为 stopped_by_admin。
    @note 停用不释放端口，避免旧配置端口被其他用户立即占用。
    """

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
    """@brief 管理员恢复指定代理。
    @param proxy_id 代理 ID。
    @return ok=true 表示状态已切回 active。
    @throws HTTPException 用户余额不足或 TCP 端口已被占用时返回 400。
    @note 恢复 TCP 代理会重新预留缺失的 remotePort。
    """

    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.status == ProxyStatus.DELETED:
            raise HTTPException(status_code=404, detail="proxy not found")
        user = store.users.get(proxy.uid)
        if user is None or user.balance_mb <= 0:
            raise HTTPException(status_code=400, detail="余额不足")
        if proxy.proxy_type == ProxyType.TCP:
            occupied = []
            remote_ports = [mapping.remote_port for mapping in proxy.tcp_mappings]
            for remote_port in remote_ports:
                owner = store.find_proxy_by_remote_port_unlocked(remote_port)
                if owner is not None and owner.id != proxy.id:
                    occupied.append(remote_port)
            if occupied:
                raise HTTPException(status_code=400, detail=f"端口已被占用: {sorted(occupied)}")
            to_reserve = [port for port in remote_ports if port_pool.is_port_unreserved(port)]
            if to_reserve:
                unavailable = port_pool.reserve_many(to_reserve)
                if unavailable:
                    raise HTTPException(status_code=400, detail=f"公网端口不可用: {sorted(unavailable)}")
        proxy.status = ProxyStatus.ACTIVE
    return {"ok": True}


@router.delete("/proxies/{proxy_id}", dependencies=[Depends(require_admin)])
async def delete_proxy(proxy_id: int) -> dict[str, bool]:
    """@brief 管理员物理删除指定代理记录。
    @param proxy_id 代理 ID。
    @return ok=true 表示删除完成。
    @note TCP 代理删除时会释放全部公网端口；普通用户删除则保留逻辑删除记录。
    """

    async with store.lock:
        proxy = store.proxies.pop(proxy_id, None)
        if proxy is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        if proxy.proxy_type == ProxyType.TCP:
            port_pool.release_many([mapping.remote_port for mapping in proxy.tcp_mappings])
    return {"ok": True}
