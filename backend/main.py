"""@file backend/main.py
@brief 创建 FastAPI 应用，注册 API 路由，挂载静态资源，并管理后台生命周期。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：FastAPI、静态文件服务、frps 管理器、轮询器、脚本渲染器。
  修改记录：2026-06-10，补充 Doxygen 风格文件头、生命周期和路由说明。
  启动时加载脚本模板、恢复注册用户、启动 frps 管理器和流量轮询器。
  关闭时先停止轮询器，再停止 frps，避免退出时继续访问已释放的资源。
  /user、/admin、/show 返回三个前端页面。
  /frontend 和 /static 挂载静态资源。
  /mock_api.js 会把开发模式 mock 开关替换为 false，生产页面默认访问真实 API。
  页面文件不存在时返回明确的 404 HTML，而不是抛出未捕获文件错误。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.config import ROOT_DIR
from backend.deps import port_pool, settings
from backend.frps_client import FrpsClient
from backend.frps_manager import FrpsManager
from backend.plugin_handler import router as plugin_router
from backend.poller import UsagePoller
from backend.routes import admin_api, show_api, user_api
from backend.script_renderer import script_renderer
from backend.user_persistence import load_registered_users_unlocked
from backend.models import store


frps_manager = FrpsManager(settings)
usage_poller = UsagePoller(FrpsClient(settings), settings.usage_poll_interval_sec)


@asynccontextmanager
async def lifespan(app: FastAPI):
    script_renderer.load()
    async with store.lock:
        load_registered_users_unlocked(store)
        _reserve_loaded_tcp_ports_unlocked()
    await frps_manager.start()
    usage_poller.start()
    try:
        yield
    finally:
        await usage_poller.stop()
        await frps_manager.stop()


def _reserve_loaded_tcp_ports_unlocked() -> None:
    ports = [
        mapping.remote_port
        for proxy in store.proxies.values()
        if proxy.status != "deleted"
        for mapping in proxy.tcp_mappings
    ]
    if ports:
        port_pool.reserve_many(ports)


app = FastAPI(title="BearFrps Platform", lifespan=lifespan)
app.include_router(user_api.router)
app.include_router(admin_api.router)
app.include_router(show_api.router)
app.include_router(plugin_router)

def _mount_static(app_: FastAPI, route: str, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    app_.mount(route, StaticFiles(directory=str(path)), name=route.strip("/"))


def _html_file(relative: str, fallback: str):
    path = ROOT_DIR / relative
    if path.exists():
        return FileResponse(path)
    return HTMLResponse(f'<meta charset="utf-8"><p>{fallback}</p>', status_code=404)


_mount_static(app, "/frontend", ROOT_DIR / "frontend")
_mount_static(app, "/static", ROOT_DIR / "static")


@app.get("/")
async def index():
    return HTMLResponse(
        '<meta charset="utf-8"><a href="/user">用户端</a> '
        '<a href="/admin">管理端</a> <a href="/show">展示页</a>'
    )


@app.get("/user")
async def user_page():
    return _html_file("frontend/user.html", "user page is not ready")


@app.get("/admin")
async def admin_page():
    return _html_file("frontend/admin.html", "admin page is not ready")


@app.get("/show")
async def show_page():
    return _html_file("frontend/show.html", "show page is not ready")


@app.get("/shared.css")
async def shared_css():
    path = ROOT_DIR / "frontend/shared.css"
    if path.exists():
        return FileResponse(path, media_type="text/css")
    return Response("/* shared.css is not ready */", media_type="text/css", status_code=404)


@app.get("/mock_api.js")
async def mock_api_js():
    path = ROOT_DIR / "frontend/mock_api.js"
    if not path.exists():
        return Response("// mock_api.js is not ready\n", media_type="application/javascript", status_code=404)
    text = path.read_text(encoding="utf-8").replace("window.USE_MOCK = true;", "window.USE_MOCK = false;", 1)
    return Response(text, media_type="application/javascript")
