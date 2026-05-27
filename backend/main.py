from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.config import ROOT_DIR
from backend.deps import settings
from backend.frps_client import FrpsClient
from backend.frps_manager import FrpsManager
from backend.plugin_handler import router as plugin_router
from backend.poller import UsagePoller
from backend.routes import admin_api, show_api, user_api
from backend.script_renderer import script_renderer


frps_manager = FrpsManager(settings)
usage_poller = UsagePoller(FrpsClient(settings), settings.usage_poll_interval_sec)


@asynccontextmanager
async def lifespan(app: FastAPI):
    script_renderer.load()
    await frps_manager.start()
    usage_poller.start()
    try:
        yield
    finally:
        await usage_poller.stop()
        await frps_manager.stop()


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
