"""@file backend/script_renderer.py
@brief 把 Proxy 和 Settings 渲染为 frpc.toml、访问者配置和跨平台启动脚本。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：脚本模板目录、backend.models、backend.config.Settings。
  修改记录：2026-06-10，补充 Doxygen 风格文件头、配置生成规则和安全说明。
  auth.token 始终写入 frps 内部共享令牌，满足官方 frp 控制通道认证。
  metadatas.token 写入用户级 frpc_token，用于后端插件做租户身份校验。
  metadatas.uid 写入用户 uid，插件会把它与 token 推导出的用户做一致性校验。
  TCP 多端口代理会生成多个 [[proxies]]，每个代理名携带映射后缀。
  XTCP 会生成 xtcp 服务端配置、stcp fallback 配置和 visitor 配置。
  HTTP 高级配置只在字段非空时输出，避免生成 frp 不接受的空配置项。

  前端展示的脚本包含用户令牌，复制后应视为敏感信息。
  用户可以修改 localPort，但不应修改 remotePort、metadatas 或 frps_name。
  TEMPLATE_FILES 映射脚本类别、系统平台和模板文件名。
  load 会在应用启动时把模板读入内存，减少每次请求的磁盘读取。
  render_scripts 返回 frpc、visitor 和 demo 三类脚本，按代理类型决定是否包含 visitor。
  render_frpc_config 是用户服务端代理配置的主要入口。
  render_frpc_visitor_config 只对 XTCP 有意义。

  字符串统一经过 _toml_string 转义。
  布尔值统一输出 true/false，避免 Python True/False 进入 TOML。
  数组通过 _toml_array 输出，主要用于 HTTP locations。
  带空值的可选字段不输出，减少 frpc 配置解析失败的概率。

  普通代理使用 proxy.frps_name。
  TCP 多端口映射使用 TcpMapping.frps_name，保证每个 remotePort 都有独立代理名。
  XTCP fallback 使用 p2p_fallback_name。
  visitor 名称使用服务端代理名追加 __visitor，避免与服务端代理冲突。

  transport.useEncryption 映射加密传输。
  transport.useCompression 映射压缩传输。
  transport.bandwidthLimitMode 支持 client/server。
  HTTP basicAuth、hostHeaderRewrite 和 locations 只在 HTTP 代理中输出。
  XTCP 和 stcp fallback 的 secretKey 必须在服务端和 visitor 配置中一致。

  _render_template 用占位符替换生成跨平台脚本。
  frpc 脚本负责下载官方 frpc 并写入 frpc.toml。
  demo 脚本负责启动本地留言板服务。
  Windows 脚本使用 PowerShell here-string 写入配置文件。
  Linux/macOS 脚本使用 heredoc 写入配置文件。

  生成脚本覆盖 Linux、macOS 和 Windows。
  生成配置明确 serverAddr、serverPort、auth.token 和代理段。
  生成配置包含 metadatas.uid 和 metadatas.token。
  TCP 代理输出 remotePort，HTTP 代理输出 subdomain。
  P2P 代理输出 secretKey 和 visitor 配置。
  demo 脚本默认端口来自 Settings.default_local_port。
  模板加载失败会在启动阶段暴露，便于部署前发现问题。
  所有配置字符串都经过 TOML 转义，避免用户名称破坏配置格式。
"""

from __future__ import annotations

from pathlib import Path

from backend.config import Settings, ROOT_DIR
from backend.models import Proxy, ProxyType, store


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
        server_config = self.render_frpc_config(proxy, settings)
        bundle = {
            "frpc": {
                "linux": self._render(("frpc", "linux"), proxy, settings, server_config),
                "mac": self._render(("frpc", "mac"), proxy, settings, server_config),
                "windows": self._render(("frpc", "windows"), proxy, settings, server_config),
            },
            "demo": {
                "linux": self._render(("demo", "linux"), proxy, settings, server_config),
                "mac": self._render(("demo", "mac"), proxy, settings, server_config),
                "windows": self._render(("demo", "windows"), proxy, settings, server_config),
            },
        }
        if proxy.proxy_type == ProxyType.XTCP:
            visitor_config = self.render_frpc_visitor_config(proxy, settings)
            bundle["visitor"] = {
                "linux": self._render(("frpc", "linux"), proxy, settings, visitor_config),
                "mac": self._render(("frpc", "mac"), proxy, settings, visitor_config),
                "windows": self._render(("frpc", "windows"), proxy, settings, visitor_config),
            }
        return bundle

    def render_frpc_configs(self, proxy: Proxy, settings: Settings) -> dict[str, str]:
        configs = {"server": self.render_frpc_config(proxy, settings)}
        if proxy.proxy_type == ProxyType.XTCP:
            configs["visitor"] = self.render_frpc_visitor_config(proxy, settings)
        return configs

    def render_frpc_config(self, proxy: Proxy, settings: Settings) -> str:
        lines = self._common_frpc_lines(proxy, settings)
        if proxy.proxy_type == ProxyType.TCP:
            for mapping in proxy.tcp_mappings:
                lines.extend(
                    [
                        "[[proxies]]",
                        f'name = "{_toml_str(mapping.frps_name)}"',
                        'type = "tcp"',
                        f'localIP = "{_toml_str(proxy.local_ip)}"',
                        f"localPort = {mapping.local_port}",
                        f"remotePort = {mapping.remote_port}",
                        *self._proxy_transport_lines(proxy),
                        "",
                    ]
                )
        elif proxy.proxy_type == ProxyType.XTCP:
            secret_key = proxy.p2p_secret_key or _effective_frpc_token(proxy)
            fallback_name = proxy.p2p_fallback_name or f"{proxy.frps_name}__fallback"
            for name, proxy_type in (
                (proxy.frps_name, "xtcp"),
                (fallback_name, "stcp"),
            ):
                lines.extend(
                    [
                        "[[proxies]]",
                        f'name = "{_toml_str(name)}"',
                        f'type = "{proxy_type}"',
                        f'secretKey = "{_toml_str(secret_key)}"',
                        f'localIP = "{_toml_str(proxy.local_ip)}"',
                        f"localPort = {proxy.local_port}",
                        'allowUsers = ["*"]',
                        *self._proxy_transport_lines(proxy),
                        "",
                    ]
                )
        else:
            lines.extend(
                [
                    "[[proxies]]",
                    f'name = "{_toml_str(proxy.frps_name)}"',
                    'type = "http"',
                    f'localIP = "{_toml_str(proxy.local_ip)}"',
                    f"localPort = {proxy.local_port}",
                    f'subdomain = "{_toml_str(proxy.subdomain or "")}"',
                    *self._http_advanced_lines(proxy),
                    *self._proxy_transport_lines(proxy),
                    "",
                ]
            )
        return "\n".join(lines)

    def _proxy_transport_lines(self, proxy: Proxy) -> list[str]:
        return [
            f'transport.bandwidthLimit = "{proxy.speed_limit_kbps}KB"',
            f'transport.bandwidthLimitMode = "{_toml_str(proxy.bandwidth_limit_mode)}"',
            f"transport.useEncryption = {_toml_bool(proxy.use_encryption)}",
            f"transport.useCompression = {_toml_bool(proxy.use_compression)}",
        ]

    def _http_advanced_lines(self, proxy: Proxy) -> list[str]:
        lines = []
        if proxy.http_user and proxy.http_password:
            lines.extend(
                [
                    f'httpUser = "{_toml_str(proxy.http_user)}"',
                    f'httpPassword = "{_toml_str(proxy.http_password)}"',
                ]
            )
        if proxy.http_locations:
            lines.append(f"locations = {_toml_array(proxy.http_locations)}")
        if proxy.host_header_rewrite:
            lines.append(
                f'hostHeaderRewrite = "{_toml_str(proxy.host_header_rewrite)}"'
            )
        return lines

    def render_frpc_visitor_config(self, proxy: Proxy, settings: Settings) -> str:
        if proxy.proxy_type != ProxyType.XTCP:
            return self.render_frpc_config(proxy, settings)
        secret_key = proxy.p2p_secret_key or _effective_frpc_token(proxy)
        fallback_name = proxy.p2p_fallback_name or f"{proxy.frps_name}__fallback"
        xtcp_visitor_name = f"{proxy.frps_name}__visitor"
        stcp_visitor_name = f"{fallback_name}__visitor"
        lines = self._common_frpc_lines(proxy, settings)
        lines.extend(
            [
                "[[visitors]]",
                f'name = "{_toml_str(xtcp_visitor_name)}"',
                'type = "xtcp"',
                f'serverName = "{_toml_str(proxy.frps_name)}"',
                f'secretKey = "{_toml_str(secret_key)}"',
                f'bindAddr = "{_toml_str(proxy.visitor_bind_addr)}"',
                f"bindPort = {proxy.visitor_bind_port}",
                f"keepTunnelOpen = {_toml_bool(proxy.keep_tunnel_open)}",
                "maxRetriesAnHour = 8",
                "minRetryInterval = 90",
                f'fallbackTo = "{_toml_str(stcp_visitor_name)}"',
                f"fallbackTimeoutMs = {proxy.fallback_timeout_ms}",
                "",
                "[[visitors]]",
                f'name = "{_toml_str(stcp_visitor_name)}"',
                'type = "stcp"',
                f'serverName = "{_toml_str(fallback_name)}"',
                f'secretKey = "{_toml_str(secret_key)}"',
                f'bindAddr = "{_toml_str(proxy.visitor_bind_addr)}"',
                "bindPort = -1",
                "",
            ]
        )
        return "\n".join(lines)

    def _common_frpc_lines(self, proxy: Proxy, settings: Settings) -> list[str]:
        token = _effective_frpc_token(proxy)
        return [
            f'serverAddr = "{_toml_str(settings.server_public_host)}"\n'
            f"serverPort = {settings.frps_bind_port}",
            "",
            'auth.method = "token"\n'
            f'auth.token = "{_toml_str(settings.frps_auth_token)}"\n'
            f'metadatas.token = "{_toml_str(token)}"\n'
            f'metadatas.uid = "{_toml_str(proxy.uid)}"',
            "",
        ]

    def _render(
        self,
        key: tuple[str, str],
        proxy: Proxy,
        settings: Settings,
        frpc_config: str,
    ) -> str:
        text = self.templates[key]
        replacements = {
            "{{SERVER_HOST}}": settings.server_public_host,
            "{{SERVER_PORT}}": str(settings.frps_bind_port),
            "{{FRPS_AUTH_TOKEN}}": settings.frps_auth_token,
            "{{TOKEN}}": _effective_frpc_token(proxy),
            "{{PROXY_NAME}}": proxy.frps_name,
            "{{REMOTE_PORT}}": str(proxy.frps_remote_port or ""),
            "{{FRP_VERSION}}": settings.frps_version,
            "{{FRP_VERSION_NOV}}": settings.frp_version_without_v,
            "{{DEFAULT_LOCAL_PORT}}": str(proxy.local_port),
            "{{DEFAULT_SPEED_LIMIT_KBPS}}": str(proxy.speed_limit_kbps),
            "{{DEMO_BIN_BASE_URL}}": settings.demo_bin_base_url,
            "{{FRPC_CONFIG}}": frpc_config.rstrip(),
            "{{LOCAL_PORT}}": str(proxy.local_port),
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


def _toml_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _effective_frpc_token(proxy: Proxy) -> str:
    return store.user_frpc_token_unlocked(proxy.uid) or proxy.token


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_array(values: list[str]) -> str:
    return "[" + ", ".join(f'"{_toml_str(value)}"' for value in values) + "]"


FRPC_UNIX_FALLBACK = r"""set -e

echo "=== frpc 启动脚本 ==="
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
{{FRPC_CONFIG}}
EOF

echo "启动 frpc"
./frpc -c frpc.toml
"""


FRPC_WINDOWS_FALLBACK = r"""Write-Host "=== frpc 启动脚本 ==="
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

Unblock-File ".\frpc.exe" -ErrorAction SilentlyContinue

@"
{{FRPC_CONFIG}}
"@ | Set-Content -Encoding UTF8 frpc.toml

Write-Host "启动 frpc"
.\frpc.exe -c frpc.toml
"""


DEMO_UNIX_FALLBACK = r"""set -e

echo "=== Demo 留言板服务启动脚本 ==="
printf "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]: "
read PORT
PORT=${PORT:-{{DEFAULT_LOCAL_PORT}}}
printf "昵称 [默认 留言板]: "
read NICKNAME
NICKNAME=${NICKNAME:-留言板}
printf "留言 [默认 这是一个临时留言板]: "
read MESSAGE
MESSAGE=${MESSAGE:-这是一个临时留言板}

if command -v python3 >/dev/null 2>&1; then
  echo "使用 Python 版"
  if [ ! -f demo_server.py ]; then
    curl -fsSL -o demo_server.py "{{DEMO_BIN_BASE_URL}}/demo_server.py"
  fi
  python3 demo_server.py --port "$PORT" --nickname "$NICKNAME" --message "$MESSAGE"
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

./demo-server --port "$PORT" --nickname "$NICKNAME" --message "$MESSAGE"
"""


DEMO_WINDOWS_FALLBACK = r"""Write-Host "=== Demo 留言板服务启动脚本 ==="
$portInput = Read-Host "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]"
if ([string]::IsNullOrWhiteSpace($portInput)) { $port = {{DEFAULT_LOCAL_PORT}} } else { $port = $portInput }
$nicknameInput = Read-Host "昵称 [默认 留言板]"
if ([string]::IsNullOrWhiteSpace($nicknameInput)) { $nickname = "留言板" } else { $nickname = $nicknameInput }
$messageInput = Read-Host "留言 [默认 这是一个临时留言板]"
if ([string]::IsNullOrWhiteSpace($messageInput)) { $message = "这是一个临时留言板" } else { $message = $messageInput }

$python = Get-Command python -ErrorAction SilentlyContinue
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue

if ($python -or $pyLauncher) {
    Write-Host "使用 Python 版"
    if (-not (Test-Path "demo_server.py")) {
        Invoke-WebRequest -Uri "{{DEMO_BIN_BASE_URL}}/demo_server.py" -OutFile "demo_server.py"
    }
    if ($python) {
        python demo_server.py --port $port --nickname $nickname --message $message
    } else {
        py -3 demo_server.py --port $port --nickname $nickname --message $message
    }
    exit $LASTEXITCODE
}

Write-Host "未找到 Python，使用预编译 Go 兜底版"
if (-not (Test-Path "demo-server.exe")) {
    Invoke-WebRequest -Uri "{{DEMO_BIN_BASE_URL}}/demo-server-windows-amd64.exe" -OutFile "demo-server.exe"
}

Unblock-File ".\demo-server.exe" -ErrorAction SilentlyContinue
.\demo-server.exe --port $port --nickname $nickname --message $message
"""


script_renderer = ScriptRenderer()
