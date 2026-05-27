from __future__ import annotations

from pathlib import Path

from backend.config import Settings, ROOT_DIR
from backend.models import Proxy


TEMPLATE_FILES = {
    ("frpc", "linux"): "frpc.linux.sh.tmpl",
    ("frpc", "mac"): "frpc.mac.sh.tmpl",
    ("frpc", "windows"): "frpc.win.ps1.tmpl",
    ("demo", "linux"): "demo.linux.sh.tmpl",
    ("demo", "mac"): "demo.mac.sh.tmpl",
    ("demo", "windows"): "demo.win.ps1.tmpl",
}


class ScriptRenderer:
    def __init__(self, scripts_dir: Path | None = None) -> None:
        self.scripts_dir = scripts_dir or ROOT_DIR / "scripts"
        self.templates: dict[tuple[str, str], str] = {}

    def load(self) -> None:
        self.templates = {}
        for key, filename in TEMPLATE_FILES.items():
            path = self.scripts_dir / filename
            if path.exists():
                self.templates[key] = path.read_text(encoding="utf-8")
            else:
                self.templates[key] = self._fallback_template(*key)

    def render_bundle(self, proxy: Proxy, settings: Settings) -> dict[str, dict[str, str]]:
        if not self.templates:
            self.load()
        return {
            "frpc": {
                "linux": self._render(("frpc", "linux"), proxy, settings),
                "mac": self._render(("frpc", "mac"), proxy, settings),
                "windows": self._render(("frpc", "windows"), proxy, settings),
            },
            "demo": {
                "linux": self._render(("demo", "linux"), proxy, settings),
                "mac": self._render(("demo", "mac"), proxy, settings),
                "windows": self._render(("demo", "windows"), proxy, settings),
            },
        }

    def render_frpc_config(self, proxy: Proxy, settings: Settings) -> str:
        return (
            f'serverAddr = "{settings.server_public_host}"\n'
            f"serverPort = {settings.frps_bind_port}\n\n"
            'auth.method = "token"\n'
            f'auth.token = "{settings.frps_auth_token}"\n'
            f'metadatas.token = "{proxy.token}"\n\n'
            "[[proxies]]\n"
            f'name = "{proxy.frps_name}"\n'
            'type = "tcp"\n'
            'localIP = "127.0.0.1"\n'
            f"localPort = {settings.default_local_port}\n"
            f"remotePort = {proxy.frps_remote_port}\n"
            f'transport.bandwidthLimit = "{proxy.speed_limit_kbps}KB"\n'
            'transport.bandwidthLimitMode = "server"\n'
        )

    def _render(self, key: tuple[str, str], proxy: Proxy, settings: Settings) -> str:
        text = self.templates[key]
        replacements = {
            "{{SERVER_HOST}}": settings.server_public_host,
            "{{SERVER_PORT}}": str(settings.frps_bind_port),
            "{{FRPS_AUTH_TOKEN}}": settings.frps_auth_token,
            "{{TOKEN}}": proxy.token,
            "{{PROXY_NAME}}": proxy.frps_name,
            "{{REMOTE_PORT}}": str(proxy.frps_remote_port),
            "{{FRP_VERSION}}": settings.frps_version,
            "{{FRP_VERSION_NOV}}": settings.frp_version_without_v,
            "{{DEFAULT_LOCAL_PORT}}": str(settings.default_local_port),
            "{{DEFAULT_SPEED_LIMIT_KBPS}}": str(proxy.speed_limit_kbps),
            "{{DEMO_BIN_BASE_URL}}": settings.demo_bin_base_url,
        }
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, value)
        return text

    def _fallback_template(self, bundle: str, platform: str) -> str:
        if bundle == "frpc" and platform == "windows":
            return FRPC_WINDOWS_FALLBACK
        if bundle == "frpc":
            os_name = "darwin" if platform == "mac" else "linux"
            return FRPC_UNIX_FALLBACK.replace("{{OS}}", os_name)
        if bundle == "demo" and platform == "windows":
            return DEMO_WINDOWS_FALLBACK
        os_name = "darwin" if platform == "mac" else "linux"
        tmpl = DEMO_UNIX_FALLBACK.replace("{{OS}}", os_name)
        if platform == "mac":
            tmpl = tmpl.replace(
                "当前架构 $ARCH 没有提供 Linux 兜底二进制，请安装 python3 后重试。",
                "不支持的架构: $ARCH",
            )
        return tmpl


FRPC_UNIX_FALLBACK = r"""#!/bin/bash
set -e

echo "=== frpc 启动脚本 ==="
read -p "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]: " PORT
PORT=${PORT:-{{DEFAULT_LOCAL_PORT}}}
FRP_VERSION="{{FRP_VERSION}}"
FRP_VERSION_NOV=${FRP_VERSION#v}

ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "不支持的架构: $ARCH"; exit 1 ;;
esac

OS={{OS}}

if [ ! -f frpc ]; then
  echo "下载 frpc ${FRP_VERSION}..."
  rm -rf frp_tmp
  curl -L -o /tmp/frp.tar.gz "https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/frp_${FRP_VERSION_NOV}_${OS}_${ARCH}.tar.gz"
  mkdir -p frp_tmp
  tar xzf /tmp/frp.tar.gz -C frp_tmp
  mv frp_tmp/*/frpc ./frpc
  chmod +x frpc
  rm -rf frp_tmp
  rm -f /tmp/frp.tar.gz
fi

cat > frpc.toml <<EOF
serverAddr = "{{SERVER_HOST}}"
serverPort = {{SERVER_PORT}}

auth.method = "token"
auth.token = "{{FRPS_AUTH_TOKEN}}"
metadatas.token = "{{TOKEN}}"

[[proxies]]
name = "{{PROXY_NAME}}"
type = "tcp"
localIP = "127.0.0.1"
localPort = ${PORT}
remotePort = {{REMOTE_PORT}}
transport.bandwidthLimit = "{{DEFAULT_SPEED_LIMIT_KBPS}}KB"
transport.bandwidthLimitMode = "server"
EOF

echo "启动 frpc, 公网端口 {{REMOTE_PORT}}, 本地端口 ${PORT}"
./frpc -c frpc.toml
"""


FRPC_WINDOWS_FALLBACK = r"""Write-Host "=== frpc 启动脚本 ==="
$portInput = Read-Host "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]"
if ([string]::IsNullOrWhiteSpace($portInput)) { $port = {{DEFAULT_LOCAL_PORT}} } else { $port = $portInput }
$frpVersion = "{{FRP_VERSION}}"
$frpVersionNoV = $frpVersion -replace '^v', ''

if (-not (Test-Path "frpc.exe")) {
    Write-Host "下载 frpc $frpVersion..."
    Invoke-WebRequest -Uri "https://github.com/fatedier/frp/releases/download/$frpVersion/frp_${frpVersionNoV}_windows_amd64.zip" -OutFile "frp.zip"
    Remove-Item -Recurse -Force "frp_tmp" -ErrorAction SilentlyContinue
    Expand-Archive "frp.zip" -DestinationPath "frp_tmp" -Force
    $frpcPath = Get-ChildItem -Path "frp_tmp" -Recurse -Filter "frpc.exe" | Select-Object -First 1
    if (-not $frpcPath) { throw "未找到 frpc.exe" }
    Copy-Item $frpcPath.FullName ".\frpc.exe"
    Remove-Item -Recurse -Force "frp_tmp", "frp.zip"
}

@"
serverAddr = "{{SERVER_HOST}}"
serverPort = {{SERVER_PORT}}

auth.method = "token"
auth.token = "{{FRPS_AUTH_TOKEN}}"
metadatas.token = "{{TOKEN}}"

[[proxies]]
name = "{{PROXY_NAME}}"
type = "tcp"
localIP = "127.0.0.1"
localPort = $port
remotePort = {{REMOTE_PORT}}
transport.bandwidthLimit = "{{DEFAULT_SPEED_LIMIT_KBPS}}KB"
transport.bandwidthLimitMode = "server"
"@ | Set-Content -Encoding UTF8 frpc.toml

Write-Host "启动 frpc, 公网端口 {{REMOTE_PORT}}, 本地端口 $port"
.\frpc.exe -c frpc.toml
"""


DEMO_UNIX_FALLBACK = r"""#!/bin/bash
set -e

echo "=== Demo 留言板服务启动脚本 ==="
read -p "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]: " PORT
PORT=${PORT:-{{DEFAULT_LOCAL_PORT}}}

if command -v python3 >/dev/null 2>&1; then
  echo "使用 Python 版"
  if [ ! -f demo_server.py ]; then
    curl -fsSL -o demo_server.py "{{DEMO_BIN_BASE_URL}}/demo_server.py"
  fi
  python3 demo_server.py --port "$PORT"
  exit $?
fi

echo "未找到 Python3，使用预编译 Go 兜底版"
ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "当前架构 $ARCH 没有提供 Linux 兜底二进制，请安装 python3 后重试。"; exit 1 ;;
esac

if [ ! -f demo-server ]; then
  curl -fsSL -o demo-server "{{DEMO_BIN_BASE_URL}}/demo-server-{{OS}}-${ARCH}"
  chmod +x demo-server
fi

./demo-server --port "$PORT"
"""


DEMO_WINDOWS_FALLBACK = r"""Write-Host "=== Demo 留言板服务启动脚本 ==="
$portInput = Read-Host "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]"
if ([string]::IsNullOrWhiteSpace($portInput)) { $port = {{DEFAULT_LOCAL_PORT}} } else { $port = $portInput }

$python = Get-Command python -ErrorAction SilentlyContinue
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue

if ($python -or $pyLauncher) {
    Write-Host "使用 Python 版"
    if (-not (Test-Path "demo_server.py")) {
        Invoke-WebRequest -Uri "{{DEMO_BIN_BASE_URL}}/demo_server.py" -OutFile "demo_server.py"
    }
    if ($python) {
        python demo_server.py --port $port
    } else {
        py -3 demo_server.py --port $port
    }
    exit $LASTEXITCODE
}

Write-Host "未找到 Python，使用预编译 Go 兜底版"
if (-not (Test-Path "demo-server.exe")) {
    Invoke-WebRequest -Uri "{{DEMO_BIN_BASE_URL}}/demo-server-windows-amd64.exe" -OutFile "demo-server.exe"
}
.\demo-server.exe --port $port
"""


script_renderer = ScriptRenderer()
