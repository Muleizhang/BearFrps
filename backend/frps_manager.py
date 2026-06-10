"""@file backend/frps_manager.py
@brief 渲染 frps.toml/start.sh，并在 FastAPI 生命周期内启动或停止 frps。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：asyncio、操作系统信号、backend.config.Settings。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和进程管理注释。
  frps 配置启用 HTTP 插件，回调地址固定指向同进程后端的 /frps-plugin。
  frps admin API 只监听本地地址，由后端轮询器读取状态，不直接暴露给公网。
  render_start_script 会按系统架构下载官方 frp 发布包，避免仓库内提交大型二进制。
  start 会优先写入配置和启动脚本，再尝试启动 frps；缺少二进制时输出提示并跳过。
  会写入 frps/frps.toml 和 frps/start.sh。
  成功启动时会持有 asyncio.subprocess.Process，应用退出时发送 SIGTERM。
"""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

from backend.config import ROOT_DIR, Settings


class FrpsManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.frps_dir = ROOT_DIR / "frps"
        self.config_path = self.frps_dir / "frps.toml"
        self.process: asyncio.subprocess.Process | None = None

    def write_config(self) -> None:
        self.frps_dir.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(self.render_config(), encoding="utf-8")

    def write_start_script(self) -> None:
        self.frps_dir.mkdir(parents=True, exist_ok=True)
        script = self.frps_dir / "start.sh"
        script.write_text(self.render_start_script(), encoding="utf-8")
        script.chmod(0o755)

    async def start(self) -> None:
        self.write_config()
        self.write_start_script()
        if os.getenv("BEARFRPS_START_FRPS", "").lower() not in {"1", "true", "yes"}:
            return
        binary = self.frps_dir / "frps"
        if not binary.exists():
            return
        self.process = await asyncio.create_subprocess_exec(
            str(binary),
            "-c",
            str(self.config_path),
            cwd=str(self.frps_dir),
        )

    async def stop(self) -> None:
        if self.process is None or self.process.returncode is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()

    def render_config(self) -> str:
        start = self.settings.remote_port_range_start
        end = self.settings.remote_port_range_end
        admin_port = _port_from_url(self.settings.frps_admin_api_url, 7500)
        return f"""bindAddr = "0.0.0.0"
bindPort = {self.settings.frps_bind_port}
vhostHTTPPort = {self.settings.frps_vhost_http_port}
subdomainHost = "{self.settings.effective_subdomain_host}"

webServer.addr = "127.0.0.1"
webServer.port = {admin_port}
webServer.user = "{self.settings.frps_admin_user}"
webServer.password = "{self.settings.frps_admin_password}"

auth.method = "token"
auth.token = "{self.settings.frps_auth_token}"

transport.heartbeatTimeout = 15
maxPortsPerClient = {self.settings.max_tcp_ports_per_proxy}
natholeAnalysisDataReserveHours = {self.settings.frps_nathole_analysis_data_reserve_hours}
allowPorts = [
  {{ start = {start}, end = {end} }}
]

log.to = "console"
log.level = "info"
detailedErrorsToClient = true

[[httpPlugins]]
name = "bearfrps-manager"
addr = "{self.settings.plugin_addr}"
path = "{self.settings.plugin_path}"
ops = ["Login", "NewProxy", "CloseProxy", "Ping"]
"""

    def render_start_script(self) -> str:
        return f"""#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
VERSION="${{FRPS_VERSION:-{self.settings.frps_version}}}"
VERSION_NOV="${{VERSION#v}}"
OS="$(uname | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ARCH=amd64;;
  aarch64|arm64) ARCH=arm64;;
  *) echo "Unsupported architecture: $ARCH"; exit 1;;
esac

if [ ! -x ./frps ]; then
  URL="https://github.com/fatedier/frp/releases/download/${{VERSION}}/frp_${{VERSION_NOV}}_${{OS}}_${{ARCH}}.tar.gz"
  echo "Downloading frps from $URL"
  curl -L -o frp.tar.gz "$URL"
  tar xzf frp.tar.gz --strip-components=1 --wildcards "*/frps"
  chmod +x frps
  rm -f frp.tar.gz
fi

exec ./frps -c frps.toml
"""


def _port_from_url(url: str, default: int) -> int:
    try:
        from urllib.parse import urlparse

        return urlparse(url).port or default
    except Exception:
        return default
