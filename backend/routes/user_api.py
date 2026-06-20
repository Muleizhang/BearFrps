"""@file backend/routes/user_api.py
@brief 提供用户注册登录、余额充值、frpc 令牌、代理申请、脚本获取和删除接口。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：FastAPI、pydantic、认证模块、端口池、脚本渲染器、用户持久化。
  修改记录：2026-06-10，补充 Doxygen 风格文件头、接口说明和代理创建业务规则。
  /api/user/register 和 /login 创建用户会话。
  /api/user/me 返回当前登录用户公开信息。
  /api/user/frpc-token 和 /rotate 管理用户级 frpc 令牌。
  /api/proxies 支持创建、列表、删除和重新获取脚本。
  创建代理前检查余额、连接数、名称唯一性、端口范围和高级配置。
  TCP 支持 auto/single/range 三种端口模式，并写入 tcp_mappings。
  HTTP 代理使用 subdomain 生成公开访问 URL。
  XTCP 生成 xtcp 服务端代理、stcp fallback 代理和 visitor 脚本。
  TCP/HTTP 创建成功后扣减用户余额，删除代理不退还已分配流量。

  用户输入不合法返回 HTTP 400。
  未登录用户由 require_user 返回 HTTP 401。
  操作非本人代理返回 HTTP 404，避免泄露其他用户资源是否存在。
  RegisterRequest 只接收 username/password，用户名会在认证层规范化。
  LoginRequest 与注册共用密码校验逻辑，避免登录路径绕过基础规则。
  TcpPortsRequest 表达 auto/single/range 三种端口分配模式。
  AdvancedConfigRequest 表达传输加密、压缩、HTTP 认证和 P2P fallback 设置。
  CreateProxyRequest 是前端创建表单的统一入口，具体字段按 proxy_type 生效。

  读取当前用户并进入 store.lock。
  校验用户余额是否足够支付 traffic_mb。
  校验连接数量是否超过 max_connections_per_user。
  校验同一用户下代理名称是否重复。
  按 proxy_type 分派到 TCP、HTTP 或 XTCP 参数构建逻辑。
  成功创建 TCP/HTTP Proxy 后扣减余额并保存用户数据。
  退出锁后渲染 frpc 配置和脚本，返回给前端弹窗展示。

  auto 模式从端口池申请 count 个连续可用端口。
  single 模式校验用户指定 remote_port 在合法范围且未占用。
  range 模式校验 remote_start_port 到 remote_end_port 连续且数量不超过上限。
  local_start_port 需要保证映射后的本地端口不超过 65535。
  任一端口预留失败时必须回滚已预留端口。

  subdomain 会拼接 effective_subdomain_host 生成公开 URL。
  locations、host_header_rewrite、http_user/http_password 作为高级配置输出。
  HTTP 代理不占用 TCP 端口池，因此不影响管理员端口范围收缩。

  secretKey 使用用户级令牌或代理字段派生，visitor 配置必须一致。
  stcp fallback 代理用于 XTCP 无法打洞时的回退连接。
  fallback 不占用平台公网 TCP 端口池，visitor_bind_port 只在用户本机监听。
  visitor_bind_port 是用户本地访问端口，不进入平台端口池。

  响应中的 proxy 是安全 DTO，不直接暴露 password_hash。
  frpc_config 是当前服务端配置快照，用户轮换令牌后需要重新获取。
  scripts 按 linux/mac/windows 分组，前端只负责复制或下载。
  删除代理返回 ok=true，端口释放在后端同步完成。

  用户接口覆盖注册、登录、退出、查询当前用户。
  流量接口覆盖免费充值和余额扣减。
  令牌接口覆盖查询和轮换。
  代理接口覆盖创建、列表、脚本获取和删除。
  创建代理时同时返回配置和脚本，满足课程演示开箱即用要求。
  创建失败返回明确错误，满足可测性和可调试性要求。
  删除代理释放端口，满足端口池复用要求。
  获取脚本会重新渲染当前 token，满足令牌轮换后恢复连接要求。
  所有用户操作都依赖 require_user，满足访问控制要求。
  管理端操作不在本模块实现，保持用户/管理员边界清晰。

  name 去除首尾空白。
  traffic_mb 必须为正数。
  speed_limit_kbps 使用默认值或用户指定值。
  proxy_type 只允许受支持类型。
  remote_port 必须在 1 到 65535。
  allocatable 端口必须在管理员配置范围内。
  local_port 必须在 1 到 65535。
  subdomain 需要小写并符合域名片段规则。
  locations 需要解析为路径列表。
  bandwidth_limit_mode 只允许 client 或 server。
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

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
from backend.models import (
    Proxy,
    ProxyStatus,
    ProxyType,
    TcpMapping,
    User,
    new_token,
    now_utc,
    store,
)
from backend.script_renderer import script_renderer
from backend.user_persistence import save_registered_users_unlocked


def _add_public_url(dto: dict[str, object]) -> dict[str, object]:
    """@brief 为代理 DTO 补充前端展示用访问地址。
    @param dto store 输出的代理字典，会被原地补充 public_url/public_urls。
    @return 补充访问地址后的同一个 DTO。
    @note XTCP 需要 visitor 脚本连接，不暴露可直接点击的公网 URL。
    """

    if dto.get("proxy_type") == ProxyType.HTTP.value:
        subdomain = dto.get("subdomain")
        if subdomain:
            port = settings.public_vhost_http_port
            port_part = "" if port == 80 else f":{port}"
            dto["public_url"] = (
                f"http://{subdomain}.{settings.effective_subdomain_host}{port_part}/"
            )
        else:
            dto["public_url"] = None
        dto["public_urls"] = [dto["public_url"]] if dto["public_url"] else []
    elif dto.get("proxy_type") == ProxyType.XTCP.value:
        dto["public_urls"] = []
        dto["public_url"] = None
    else:
        public_urls = []
        mappings = dto.get("tcp_mappings")
        if isinstance(mappings, list):
            for mapping in mappings:
                if isinstance(mapping, dict) and mapping.get("remote_port") is not None:
                    public_urls.append(
                        f"http://{settings.server_public_host}:{mapping['remote_port']}/"
                    )
        remote_port = dto.get("frps_remote_port")
        if not public_urls and remote_port is not None:
            public_urls.append(f"http://{settings.server_public_host}:{remote_port}/")
        dto["public_urls"] = public_urls
        dto["public_url"] = public_urls[0] if public_urls else None
    return dto


router = APIRouter()
_LOCAL_IP_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_HOST_HEADER_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}(?::[0-9]{1,5})?$")


class TcpPortsRequest(BaseModel):
    """@brief TCP 代理的公网端口和本地端口映射请求。
    @note auto 由端口池分配连续公网端口，single/range 需要显式校验并预留。
    """

    mode: Literal["auto", "single", "range"] = "auto"
    mapping_mode: Literal["many-to-one", "many-to-many"] = "many-to-one"
    count: int | None = Field(default=None, ge=1)
    local_start_port: int | None = Field(default=None, ge=1, le=65535)
    remote_port: int | None = Field(default=None, ge=1, le=65535)
    local_port: int | None = Field(default=None, ge=1, le=65535)
    remote_start_port: int | None = Field(default=None, ge=1, le=65535)
    remote_end_port: int | None = Field(default=None, ge=1, le=65535)


class AdvancedConfigRequest(BaseModel):
    """@brief 传输、HTTP 和 XTCP visitor 的高级配置请求。
    @note HTTP 认证字段必须成对出现，fallback 超时只影响 XTCP visitor。
    """

    use_encryption: bool = False
    use_compression: bool = False
    bandwidth_limit_mode: str = "server"
    http_user: str | None = Field(default=None, max_length=64)
    http_password: str | None = Field(default=None, max_length=128)
    http_locations: list[str] | None = None
    host_header_rewrite: str | None = Field(default=None, max_length=260)
    keep_tunnel_open: bool | None = None
    fallback_timeout_ms: int | None = None


class CreateProxyRequest(BaseModel):
    """@brief 创建代理的用户请求体。
    @note 字段按 proxy_type 生效，TCP 使用 tcp_ports，HTTP 使用 subdomain，XTCP 使用 visitor_bind_port。
    """

    name: str = Field(min_length=1, max_length=20)
    proxy_type: ProxyType = ProxyType.TCP
    traffic_mb: int = Field(gt=0)
    speed_limit_kbps: int | None = Field(default=None, gt=0)
    local_ip: str | None = None
    local_port: int | None = Field(default=None, ge=1, le=65535)
    subdomain: str | None = None
    tcp_ports: TcpPortsRequest | None = None
    visitor_bind_port: int | None = Field(default=None, ge=1, le=65535)
    advanced_config: AdvancedConfigRequest | None = None


class UpdateProxyRequest(BaseModel):
    """@brief 修改代理的用户请求体。
    @note 不允许修改 proxy_type 和公网 remotePort，避免已发脚本和端口池状态失配。
    """

    name: str | None = Field(default=None, min_length=1, max_length=20)
    traffic_mb: int | None = Field(default=None, gt=0)
    speed_limit_kbps: int | None = Field(default=None, gt=0)
    local_ip: str | None = None
    local_port: int | None = Field(default=None, ge=1, le=65535)
    subdomain: str | None = None
    visitor_bind_port: int | None = Field(default=None, ge=1, le=65535)
    advanced_config: AdvancedConfigRequest | None = None


class UserAuthRequest(BaseModel):
    """@brief 用户注册和登录共用的账号密码请求体。"""

    username: str
    password: str


@router.post("/api/user/register")
async def register(
    body: UserAuthRequest,
    response: Response,
    legacy_uid: Annotated[str | None, Cookie(alias="uid")] = None,
) -> dict[str, object]:
    """@brief 注册账号并建立用户会话。
    @param body 用户名和密码。
    @param response FastAPI 响应对象，用于写入 session cookie。
    @param legacy_uid 历史匿名 UID cookie，用于把旧演示数据绑定到新账号。
    @return 当前用户的公开 DTO。
    """

    async with store.lock:
        user = register_user_unlocked(body.username, body.password, legacy_uid)
    create_user_session(response, user)
    return user_public_dto(user)


@router.post("/api/user/login")
async def login(body: UserAuthRequest, response: Response) -> dict[str, object]:
    """@brief 校验账号密码并建立用户会话。
    @param body 用户名和密码。
    @param response FastAPI 响应对象，用于写入 session cookie。
    @return 当前用户的公开 DTO。
    @throws HTTPException 用户不存在或密码错误时返回 401。
    """

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
    """@brief 清除当前用户会话 cookie。
    @param request FastAPI 请求对象，用于读取待清理 session。
    @param response FastAPI 响应对象，用于删除 cookie。
    @return ok=true 表示退出流程完成。
    """

    clear_user_session(response, request.cookies.get(USER_SESSION_COOKIE))
    return {"ok": True}


@router.get("/api/user/me")
async def current_user(user: User = Depends(require_user)) -> dict[str, object]:
    """@brief 返回当前登录用户的公开信息。
    @param user require_user 解析出的已登录用户。
    @return 不包含密码哈希和 frpc 令牌的用户 DTO。
    """

    return user_public_dto(user)


@router.post("/api/user/init")
async def init_user(user: User = Depends(require_user)) -> dict[str, object]:
    """@brief 兼容旧前端初始化入口。
    @param user require_user 解析出的已登录用户。
    @return 与 /api/user/me 相同的用户 DTO。
    """

    return user_public_dto(user)


@router.post("/api/user/recharge")
async def recharge(user: User = Depends(require_user)) -> dict[str, int]:
    """@brief 给当前用户发放一次课堂演示免费流量。
    @param user require_user 解析出的已登录用户。
    @return 更新后的余额和累计充值量。
    @note 充值记录和余额在同一个 store.lock 临界区内保存。
    """

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


@router.get("/api/user/frpc-token")
async def get_frpc_token(user: User = Depends(require_user)) -> dict[str, object]:
    """@brief 查询当前用户的 frpc 元数据令牌。
    @param user require_user 解析出的已登录用户。
    @return token、版本号和最近轮换时间。
    @note 查询时同步历史代理 token 字段，兼容旧脚本生成逻辑。
    """

    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        store.sync_user_proxy_tokens_unlocked(current.uid)
        return _frpc_token_response(current)


@router.post("/api/user/frpc-token/rotate")
async def rotate_frpc_token(user: User = Depends(require_user)) -> dict[str, object]:
    """@brief 轮换当前用户的 frpc 元数据令牌。
    @param user require_user 解析出的已登录用户。
    @return 新 token、版本号和轮换时间。
    @note 旧脚本会在后续 Login/Ping 中被插件拒绝，用户需要重新获取脚本。
    """

    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        current.frpc_token = new_token()
        current.frpc_token_version += 1
        current.frpc_token_rotated_at = now_utc()
        store.sync_user_proxy_tokens_unlocked(current.uid)
        save_registered_users_unlocked(store)
        return _frpc_token_response(current)


@router.get("/api/proxies")
async def list_proxies(user: User = Depends(require_user)) -> dict[str, list[dict[str, object]]]:
    """@brief 列出当前用户名下的代理。
    @param user require_user 解析出的已登录用户。
    @return proxies 数组，元素为普通用户安全 DTO。
    """

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
    """@brief 创建代理并返回 frpc 配置和启动脚本。
    @param body 创建代理请求体。
    @param response 保留给 FastAPI 依赖注入，当前不直接写入响应头。
    @param user require_user 解析出的已登录用户。
    @return proxy DTO、frpc 配置和跨平台脚本 bundle。
    @throws HTTPException 余额不足、端口不可用、名称或子域名冲突时返回 400。
    @note TCP 端口预留、TCP/HTTP 余额扣减和持久化必须在 store.lock 内完成。
    """

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    local_ip = _normalize_local_ip(body.local_ip)
    local_port = body.local_port or settings.default_local_port
    subdomain = _normalize_subdomain(body.subdomain) if body.proxy_type == ProxyType.HTTP else None
    visitor_bind_port = body.visitor_bind_port or 9001
    advanced_config = _normalize_advanced_config(body.proxy_type, body.advanced_config)

    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        if body.traffic_mb > current.balance_mb:
            raise HTTPException(status_code=400, detail="余额不足")
        if store.user_has_name_unlocked(current.uid, name):
            raise HTTPException(status_code=400, detail="名称重复")
        if store.active_connection_count_unlocked(current.uid) >= settings.max_connections_per_user:
            raise HTTPException(status_code=400, detail="超过最大连接数")

        remote_port = None
        tcp_mappings: list[TcpMapping] = []
        if body.proxy_type == ProxyType.TCP:
            remote_ports, local_ports = _allocate_tcp_ports(body, local_port)
        elif store.find_proxy_by_subdomain_unlocked(subdomain):
            raise HTTPException(status_code=400, detail="子域名已被占用")

        proxy_id = store.next_proxy_id_unlocked()
        frps_name = f"{current.uid}__{proxy_id}"
        if body.proxy_type == ProxyType.TCP:
            tcp_mappings = [
                TcpMapping(
                    frps_name=_tcp_mapping_name(frps_name, index),
                    remote_port=remote_port_item,
                    local_port=local_port_item,
                    actual_local_port=local_port_item,
                )
                for index, (remote_port_item, local_port_item) in enumerate(
                    zip(remote_ports, local_ports, strict=True)
                )
            ]
            remote_port = tcp_mappings[0].remote_port
            local_port = tcp_mappings[0].local_port
        p2p_secret_key = new_token() if body.proxy_type == ProxyType.XTCP else None
        p2p_fallback_name = (
            f"{frps_name}__fallback" if body.proxy_type == ProxyType.XTCP else None
        )
        proxy = Proxy(
            id=proxy_id,
            uid=current.uid,
            name=name,
            frps_name=frps_name,
            token=current.frpc_token,
            proxy_type=body.proxy_type,
            frps_remote_port=remote_port,
            local_ip=local_ip,
            local_port=local_port,
            subdomain=subdomain,
            tcp_mappings=tcp_mappings,
            p2p_secret_key=p2p_secret_key,
            p2p_fallback_name=p2p_fallback_name,
            visitor_bind_port=visitor_bind_port,
            keep_tunnel_open=advanced_config["keep_tunnel_open"],
            fallback_timeout_ms=advanced_config["fallback_timeout_ms"],
            use_encryption=advanced_config["use_encryption"],
            use_compression=advanced_config["use_compression"],
            bandwidth_limit_mode=advanced_config["bandwidth_limit_mode"],
            http_user=advanced_config["http_user"],
            http_password=advanced_config["http_password"],
            http_locations=advanced_config["http_locations"],
            host_header_rewrite=advanced_config["host_header_rewrite"],
            actual_local_port=local_port,
            speed_limit_kbps=body.speed_limit_kbps or settings.default_speed_limit_kbps,
            traffic_limit_mb=body.traffic_mb,
        )
        store.proxies[proxy.id] = proxy
        if body.proxy_type != ProxyType.XTCP:
            current.balance_mb -= body.traffic_mb
        dto = _add_public_url(store.proxy_to_dto(proxy))
        store.proxies[proxy.id] = proxy
        save_registered_users_unlocked(store)

    return _proxy_scripts_response(proxy, dto)


@router.delete("/api/proxies/{proxy_id}")
async def delete_proxy(proxy_id: int, user: User = Depends(require_user)) -> dict[str, bool]:
    """@brief 逻辑删除当前用户的代理。
    @param proxy_id 待删除代理 ID。
    @param user require_user 解析出的已登录用户。
    @return ok=true 表示删除完成或目标已处于删除状态。
    @note TCP 代理会释放所有 tcp_mappings 的公网端口，已扣流量不退回。
    """

    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.uid != user.uid:
            raise HTTPException(status_code=404, detail="proxy not found")
        if proxy.status != ProxyStatus.DELETED:
            proxy.status = ProxyStatus.DELETED
            proxy.is_online = False
            proxy.current_speed_bps = 0
            if proxy.proxy_type == ProxyType.TCP and proxy.frps_remote_port is not None:
                port_pool.release_many([mapping.remote_port for mapping in proxy.tcp_mappings])
            save_registered_users_unlocked(store)
    return {"ok": True}


@router.patch("/api/proxies/{proxy_id}")
async def update_proxy(
    proxy_id: int,
    body: UpdateProxyRequest,
    user: User = Depends(require_user),
) -> dict[str, object]:
    """@brief 修改代理的可变配置并重新返回脚本。
    @param proxy_id 待修改代理 ID。
    @param body 修改请求体。
    @param user require_user 解析出的已登录用户。
    @return 修改后的 proxy DTO、frpc 配置和脚本 bundle。
    @note 更新 TCP 本地端口只平移 localPort，不允许改 remotePort。
    """

    async with store.lock:
        current = store.ensure_user_unlocked(user.uid)
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.uid != current.uid or proxy.status == ProxyStatus.DELETED:
            raise HTTPException(status_code=404, detail="proxy not found")

        name = body.name.strip() if body.name is not None else None
        if name is not None:
            if not name:
                raise HTTPException(status_code=400, detail="名称不能为空")
            if store.user_has_name_unlocked(current.uid, name, exclude_id=proxy.id):
                raise HTTPException(status_code=400, detail="名称重复")
            proxy.name = name

        if body.local_ip is not None:
            proxy.local_ip = _normalize_local_ip(body.local_ip)

        if body.local_port is not None:
            if proxy.proxy_type == ProxyType.TCP:
                _update_tcp_local_ports(proxy, body.local_port)
            else:
                proxy.local_port = body.local_port
                proxy.actual_local_port = body.local_port

        if body.speed_limit_kbps is not None:
            proxy.speed_limit_kbps = body.speed_limit_kbps

        if body.traffic_mb is not None:
            _update_traffic_limit_unlocked(current, proxy, body.traffic_mb)

        if proxy.proxy_type == ProxyType.HTTP and body.subdomain is not None:
            subdomain = _normalize_subdomain(body.subdomain)
            if subdomain != proxy.subdomain and store.find_proxy_by_subdomain_unlocked(
                subdomain, exclude_id=proxy.id
            ):
                raise HTTPException(status_code=400, detail="子域名已被占用")
            proxy.subdomain = subdomain

        if proxy.proxy_type == ProxyType.XTCP and body.visitor_bind_port is not None:
            proxy.visitor_bind_port = body.visitor_bind_port

        if body.advanced_config is not None:
            advanced_config = _normalize_advanced_config(proxy.proxy_type, body.advanced_config)
            proxy.use_encryption = advanced_config["use_encryption"]
            proxy.use_compression = advanced_config["use_compression"]
            proxy.bandwidth_limit_mode = advanced_config["bandwidth_limit_mode"]
            proxy.http_user = advanced_config["http_user"]
            proxy.http_password = advanced_config["http_password"]
            proxy.http_locations = advanced_config["http_locations"]
            proxy.host_header_rewrite = advanced_config["host_header_rewrite"]
            if proxy.proxy_type == ProxyType.XTCP:
                proxy.keep_tunnel_open = advanced_config["keep_tunnel_open"]
                proxy.fallback_timeout_ms = advanced_config["fallback_timeout_ms"]

        dto = _add_public_url(store.proxy_to_dto(proxy))
        save_registered_users_unlocked(store)

    return _proxy_scripts_response(proxy, dto)


@router.get("/api/proxies/{proxy_id}/scripts")
async def get_proxy_scripts(proxy_id: int, user: User = Depends(require_user)) -> dict[str, object]:
    """@brief 重新渲染指定代理的当前脚本。
    @param proxy_id 代理 ID。
    @param user require_user 解析出的已登录用户。
    @return proxy DTO、frpc 配置和跨平台脚本 bundle。
    @note 用于令牌轮换或模板更新后让用户重新复制脚本。
    """

    async with store.lock:
        proxy = store.proxies.get(proxy_id)
        if proxy is None or proxy.uid != user.uid:
            raise HTTPException(status_code=404, detail="proxy not found")
        dto = _add_public_url(store.proxy_to_dto(proxy))
    return _proxy_scripts_response(proxy, dto)


def _proxy_scripts_response(proxy: Proxy, dto: dict[str, object]) -> dict[str, object]:
    """@brief 组装创建、修改和重新获取脚本的统一响应。
    @param proxy 用于渲染配置和脚本的代理模型。
    @param dto 已按调用方权限过滤过的代理 DTO。
    @return 包含 proxy、frpc_config、frpc_configs 和 scripts 的响应字典。
    """

    frpc_config = script_renderer.render_frpc_config(proxy, settings)
    return {
        "proxy": dto,
        "frpc_config": frpc_config,
        "frpc_configs": script_renderer.render_frpc_configs(proxy, settings),
        "scripts": script_renderer.render_bundle(proxy, settings),
    }


def _frpc_token_response(user: User) -> dict[str, object]:
    """@brief 组装 frpc 用户令牌响应。
    @param user 当前用户模型。
    @return token、version 和 rotated_at 字段。
    """

    return {
        "token": user.frpc_token,
        "version": user.frpc_token_version,
        "rotated_at": user.frpc_token_rotated_at.isoformat(),
    }


def _normalize_local_ip(value: str | None) -> str:
    """@brief 校验并规范化 frpc localIP。
    @param value 用户提交的本地地址，可为空。
    @return 合法地址，空值默认 127.0.0.1。
    @throws HTTPException 地址包含非法字符或点号位置异常时返回 400。
    """

    local_ip = (value or "127.0.0.1").strip()
    if not _LOCAL_IP_RE.fullmatch(local_ip):
        raise HTTPException(status_code=400, detail="本地地址格式不合法")
    if ".." in local_ip or local_ip.startswith(".") or local_ip.endswith("."):
        raise HTTPException(status_code=400, detail="本地地址格式不合法")
    return local_ip


def _normalize_subdomain(value: str | None) -> str:
    """@brief 校验并规范化 HTTP 子域名前缀。
    @param value 用户提交的子域名前缀。
    @return 小写后的合法子域名前缀。
    @throws HTTPException 为空或不符合域名片段规则时返回 400。
    """

    subdomain = (value or "").strip().lower()
    if not subdomain:
        raise HTTPException(status_code=400, detail="请输入子域名前缀")
    if not _SUBDOMAIN_RE.fullmatch(subdomain):
        raise HTTPException(status_code=400, detail="子域名需为 3-63 位小写字母、数字或连字符")
    return subdomain


def _normalize_advanced_config(
    proxy_type: ProxyType, advanced: AdvancedConfigRequest | None
) -> dict[str, object]:
    """@brief 归一化高级配置并屏蔽与代理类型无关的字段。
    @param proxy_type 当前代理类型。
    @param advanced 用户提交的高级配置，可为空。
    @return 可直接写入 Proxy 模型的高级配置字典。
    @throws HTTPException 限速位置、HTTP 认证或 fallback 超时非法时返回 400。
    """

    config = advanced or AdvancedConfigRequest()
    if config.bandwidth_limit_mode not in ("server", "client"):
        raise HTTPException(status_code=400, detail="限速位置必须是 server 或 client")
    fallback_timeout_ms = (
        config.fallback_timeout_ms if config.fallback_timeout_ms is not None else 1000
    )
    if fallback_timeout_ms < 100 or fallback_timeout_ms > 10000:
        raise HTTPException(status_code=400, detail="fallback 超时需在 100-10000 ms 之间")
    http_user = _clean_optional(config.http_user)
    http_password = _clean_optional(config.http_password)
    if bool(http_user) != bool(http_password):
        raise HTTPException(status_code=400, detail="HTTP 认证用户名和密码需同时填写")

    http_locations: list[str] = []
    host_header_rewrite = None
    if proxy_type == ProxyType.HTTP:
        http_locations = _normalize_http_locations(config.http_locations)
        host_header_rewrite = _normalize_host_header(config.host_header_rewrite)

    return {
        "use_encryption": config.use_encryption,
        "use_compression": config.use_compression,
        "bandwidth_limit_mode": config.bandwidth_limit_mode,
        "http_user": http_user if proxy_type == ProxyType.HTTP else None,
        "http_password": http_password if proxy_type == ProxyType.HTTP else None,
        "http_locations": http_locations if proxy_type == ProxyType.HTTP else [],
        "host_header_rewrite": host_header_rewrite,
        "keep_tunnel_open": (
            config.keep_tunnel_open if config.keep_tunnel_open is not None else True
        ),
        "fallback_timeout_ms": fallback_timeout_ms,
    }


def _clean_optional(value: str | None) -> str | None:
    """@brief 去除可选字符串首尾空白并把空串转为 None。
    @param value 用户提交的可选字符串。
    @return 清理后的字符串或 None。
    """

    text = (value or "").strip()
    return text or None


def _normalize_http_locations(values: list[str] | None) -> list[str]:
    """@brief 校验 HTTP 代理的 locations 列表。
    @param values 用户提交的路径列表，可为空。
    @return 去除空项后的路径列表。
    @throws HTTPException 路径不以 / 开头、包含空白或超过 10 条时返回 400。
    """

    locations = []
    for item in values or []:
        location = str(item).strip()
        if not location:
            continue
        if not location.startswith("/"):
            raise HTTPException(status_code=400, detail="HTTP 路径必须以 / 开头")
        if any(char.isspace() for char in location):
            raise HTTPException(status_code=400, detail="HTTP 路径不能包含空白字符")
        locations.append(location)
    if len(locations) > 10:
        raise HTTPException(status_code=400, detail="HTTP 路径最多 10 条")
    return locations


def _normalize_host_header(value: str | None) -> str | None:
    """@brief 校验 HTTP hostHeaderRewrite 值。
    @param value 用户提交的 Host 或 Host:Port。
    @return 合法 Host 字符串或 None。
    @throws HTTPException 主机名或端口非法时返回 400。
    """

    host = _clean_optional(value)
    if host is None:
        return None
    if not _HOST_HEADER_RE.fullmatch(host):
        raise HTTPException(status_code=400, detail="Host 改写格式不合法")
    host_part, _, port_part = host.rpartition(":")
    if port_part and host_part:
        port = int(port_part)
        if port < 1 or port > 65535:
            raise HTTPException(status_code=400, detail="Host 改写端口不合法")
        hostname = host_part
    else:
        hostname = host
    if ".." in hostname or hostname.startswith(".") or hostname.endswith("."):
        raise HTTPException(status_code=400, detail="Host 改写格式不合法")
    return host


def _allocate_tcp_ports(
    body: CreateProxyRequest, legacy_local_port: int
) -> tuple[list[int], list[int]]:
    """@brief 根据请求模式分配或预留 TCP 公网端口。
    @param body 创建代理请求体。
    @param legacy_local_port 兼容旧前端 local_port 字段的默认本地端口。
    @return 公网端口列表和对应本地端口列表。
    @throws HTTPException 端口池不足、用户指定端口不可用或端口段非法时返回 400。
    @note single/range 会立即预留用户指定 remotePort，后续创建失败需由调用链避免。
    """

    tcp_ports = body.tcp_ports or TcpPortsRequest(
        mode="auto",
        count=1,
        local_start_port=legacy_local_port,
    )
    if tcp_ports.mode == "auto":
        count = tcp_ports.count or 1
        _validate_tcp_port_count(count)
        local_start_port = tcp_ports.local_start_port or legacy_local_port
        local_ports = _local_ports_from_start(local_start_port, count)
        remote_ports = port_pool.allocate_contiguous(count)
        if remote_ports is None:
            raise HTTPException(status_code=400, detail="端口池没有连续可用端口段")
        return remote_ports, local_ports

    if tcp_ports.mode == "single":
        if tcp_ports.remote_port is None:
            raise HTTPException(status_code=400, detail="请输入公网端口")
        if tcp_ports.local_port is None:
            raise HTTPException(status_code=400, detail="请输入本地端口")
        _reserve_requested_remote_ports([tcp_ports.remote_port])
        return [tcp_ports.remote_port], [tcp_ports.local_port]

    if tcp_ports.remote_start_port is None or tcp_ports.remote_end_port is None:
        raise HTTPException(status_code=400, detail="请输入公网端口段")
    if tcp_ports.local_start_port is None:
        raise HTTPException(status_code=400, detail="请输入本地起始端口")
    if tcp_ports.remote_start_port > tcp_ports.remote_end_port:
        raise HTTPException(status_code=400, detail="公网起始端口不能大于结束端口")
    count = tcp_ports.remote_end_port - tcp_ports.remote_start_port + 1
    _validate_tcp_port_count(count)
    remote_ports = list(range(tcp_ports.remote_start_port, tcp_ports.remote_end_port + 1))
    if tcp_ports.mapping_mode == "many-to-many":
        local_ports = _local_ports_from_start(tcp_ports.local_start_port, count)
    else:
        local_ports = [tcp_ports.local_start_port] * count
    _reserve_requested_remote_ports(remote_ports)
    return remote_ports, local_ports


def _validate_tcp_port_count(count: int) -> None:
    """@brief 校验单个 TCP 代理可绑定的端口数量。
    @param count 需要分配或预留的公网端口数量。
    @return 无返回值。
    @throws HTTPException 超过 settings.max_tcp_ports_per_proxy 时返回 400。
    """

    if count > settings.max_tcp_ports_per_proxy:
        raise HTTPException(
            status_code=400,
            detail=f"单个 TCP 配置最多 {settings.max_tcp_ports_per_proxy} 个端口",
        )


def _local_ports_from_start(start: int, count: int) -> list[int]:
    """@brief 从本地起始端口生成连续端口段。
    @param start 本地起始端口。
    @param count 端口数量。
    @return 长度为 count 的本地端口列表。
    @throws HTTPException 端口段超出 1-65535 时返回 400。
    """

    if start < 1 or start + count - 1 > 65535:
        raise HTTPException(status_code=400, detail="本地端口段必须在 1-65535 之间")
    return list(range(start, start + count))


def _update_tcp_local_ports(proxy: Proxy, local_port: int) -> None:
    """@brief 平移 TCP 多端口代理的本地端口段。
    @param proxy 待修改的 TCP 代理。
    @param local_port 新的首个本地端口。
    @return 无返回值。
    @note 只更新 local_port/actual_local_port，不改变平台分配的 remotePort。
    """

    if not proxy.tcp_mappings:
        proxy.local_port = local_port
        proxy.actual_local_port = local_port
        return
    first_local_port = proxy.tcp_mappings[0].local_port
    offset = local_port - first_local_port
    next_local_ports = [mapping.local_port + offset for mapping in proxy.tcp_mappings]
    for next_local_port in next_local_ports:
        if next_local_port < 1 or next_local_port > 65535:
            raise HTTPException(status_code=400, detail="本地端口段必须在 1-65535 之间")
    for mapping, next_local_port in zip(proxy.tcp_mappings, next_local_ports, strict=True):
        mapping.local_port = next_local_port
        mapping.actual_local_port = next_local_port
    proxy.local_port = proxy.tcp_mappings[0].local_port
    proxy.actual_local_port = proxy.tcp_mappings[0].actual_local_port


def _update_traffic_limit_unlocked(user: User, proxy: Proxy, traffic_mb: int) -> None:
    """@brief 修改代理流量额度并按增量扣减余额。
    @param user 代理所属用户，调用方已持有 store.lock。
    @param proxy 待修改代理。
    @param traffic_mb 新的代理流量额度。
    @return 无返回值。
    @throws HTTPException 新额度小于已用流量或余额不足时返回 400。
    @note XTCP 目前不扣减用户余额，与创建路径保持一致。
    """

    if traffic_mb * 1024 * 1024 < proxy.traffic_used_bytes:
        raise HTTPException(status_code=400, detail="分配流量不能小于已用流量")
    if proxy.proxy_type != ProxyType.XTCP and traffic_mb > proxy.traffic_limit_mb:
        extra_mb = traffic_mb - proxy.traffic_limit_mb
        if extra_mb > user.balance_mb:
            raise HTTPException(status_code=400, detail="余额不足")
        user.balance_mb -= extra_mb
    proxy.traffic_limit_mb = traffic_mb


def _reserve_requested_remote_ports(ports: list[int]) -> None:
    """@brief 预留用户显式指定的公网端口。
    @param ports 待预留 remotePort 列表。
    @return 无返回值。
    @throws HTTPException 任一端口不在可分配范围或已被占用时返回 400。
    """

    unavailable = port_pool.reserve_many(ports)
    if unavailable:
        raise HTTPException(
            status_code=400,
            detail=f"公网端口不可用: {sorted(unavailable)}",
        )


def _tcp_mapping_name(base_name: str, index: int) -> str:
    """@brief 生成多端口 TCP 映射的 frps 代理名。
    @param base_name 当前代理的基础 frps_name。
    @param index tcp_mappings 中的零基序号。
    @return 第一个端口使用基础名，后续端口追加 __序号。
    """

    return base_name if index == 0 else f"{base_name}__{index + 1}"
