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

webServer.addr = "127.0.0.1"
webServer.port = {admin_port}
webServer.user = "{self.settings.frps_admin_user}"
webServer.password = "{self.settings.frps_admin_password}"

auth.method = "token"
auth.token = "{self.settings.frps_auth_token}"

transport.heartbeatTimeout = 15
maxPortsPerClient = 1
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
