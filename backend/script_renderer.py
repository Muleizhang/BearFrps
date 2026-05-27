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
            f'auth.token = "{proxy.token}"\n'
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
        return DEMO_UNIX_FALLBACK.replace("{{OS}}", os_name)


FRPC_UNIX_FALLBACK = """#!/bin/bash
set -e

echo "=== frpc start ==="
read -r -p "Local port [default {{DEFAULT_LOCAL_PORT}}]: " PORT
PORT=${PORT:-{{DEFAULT_LOCAL_PORT}}}

ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH=amd64;;
  aarch64|arm64) ARCH=arm64;;
  *) echo "Unsupported architecture: $ARCH"; exit 1;;
esac

OS={{OS}}
VER={{FRP_VERSION}}
VER_NOV=${VER#v}

if [ ! -f frpc ]; then
  echo "Downloading frpc ${VER}..."
  curl -L -o frp.tar.gz "https://github.com/fatedier/frp/releases/download/${VER}/frp_${VER_NOV}_${OS}_${ARCH}.tar.gz"
  tar xzf frp.tar.gz --strip-components=1 --wildcards "*/frpc"
  chmod +x frpc
fi

cat > frpc.toml <<EOF
serverAddr = "{{SERVER_HOST}}"
serverPort = {{SERVER_PORT}}

auth.method = "token"
auth.token = "{{TOKEN}}"
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

./frpc -c frpc.toml
"""


FRPC_WINDOWS_FALLBACK = """Write-Host "=== frpc start ==="
$portInput = Read-Host "Local port [default {{DEFAULT_LOCAL_PORT}}]"
if ([string]::IsNullOrWhiteSpace($portInput)) { $port = {{DEFAULT_LOCAL_PORT}} } else { $port = $portInput }
$version = "{{FRP_VERSION}}"
$versionNoV = $version.TrimStart("v")

if (-not (Test-Path "frpc.exe")) {
    Invoke-WebRequest -Uri "https://github.com/fatedier/frp/releases/download/$version/frp_${versionNoV}_windows_amd64.zip" -OutFile "frp.zip"
    Expand-Archive "frp.zip" -DestinationPath "frp_tmp" -Force
    Copy-Item "frp_tmp\\*\\frpc.exe" "."
    Remove-Item -Recurse -Force "frp_tmp", "frp.zip"
}

@"
serverAddr = "{{SERVER_HOST}}"
serverPort = {{SERVER_PORT}}

auth.method = "token"
auth.token = "{{TOKEN}}"
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

.\\frpc.exe -c frpc.toml
"""


DEMO_UNIX_FALLBACK = """#!/bin/bash
set -e

echo "=== demo server start ==="
read -r -p "Local port [default {{DEFAULT_LOCAL_PORT}}]: " PORT
PORT=${PORT:-{{DEFAULT_LOCAL_PORT}}}

if command -v python3 >/dev/null 2>&1 && [ -f demo_server.py ]; then
  python3 demo_server.py --port "$PORT"
else
  ARCH=$(uname -m)
  case "$ARCH" in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; *) echo "Unsupported architecture: $ARCH"; exit 1;; esac
  OS={{OS}}
  BIN=demo-server
  if [ ! -f "$BIN" ]; then
    curl -L -o "$BIN" "{{DEMO_BIN_BASE_URL}}/demo-server-${OS}-${ARCH}"
    chmod +x "$BIN"
  fi
  ./"$BIN" --port "$PORT"
fi
"""


DEMO_WINDOWS_FALLBACK = """Write-Host "=== demo server start ==="
$portInput = Read-Host "Local port [default {{DEFAULT_LOCAL_PORT}}]"
if ([string]::IsNullOrWhiteSpace($portInput)) { $port = {{DEFAULT_LOCAL_PORT}} } else { $port = $portInput }

if ((Get-Command python -ErrorAction SilentlyContinue) -and (Test-Path "demo_server.py")) {
    python demo_server.py --port $port
} else {
    if (-not (Test-Path "demo-server.exe")) {
        Invoke-WebRequest -Uri "{{DEMO_BIN_BASE_URL}}/demo-server-windows-amd64.exe" -OutFile "demo-server.exe"
    }
    .\\demo-server.exe --port $port
}
"""


script_renderer = ScriptRenderer()
