你是一个全栈工程师,负责一个 frp 多租户管理平台项目的**用户本地脚本和 demo 服务**部分。
项目共有三个并行开发的部分(A 后端, B 前端, C 脚本/demo),你负责 C。

# 共享契约 v1(三方必须严格遵守,不得自行修改)

## 项目背景
基于 frps 的多租户内网穿透自助平台,课堂展示项目。单台 Debian 公网服务器部署。
本地 demo 端口默认 527(寝室门牌号),用户可在脚本启动时命令行输入修改。

## REST API 契约(后端实现,前端调用,脚本不调用)

所有 API 前缀 `/api`,JSON 收发,UTF-8。

### 用户身份
- UID 形如 `u_a1b2c3d4`,后端生成,前端用 Cookie `uid` + localStorage 双保存
- 所有 `/api/user/*` 和 `/api/proxies*` 接口从 Cookie 取 UID,无 UID 自动创建

### 接口列表

POST /api/user/init
  Req: {}
  Resp: { uid, balance_mb, total_recharged_mb, created_at }

POST /api/user/recharge
  Req: {}
  Resp: { balance_mb, total_recharged_mb }

GET  /api/proxies
  Resp: { proxies: [ProxyDTO, ...] }

POST /api/proxies
  Req: { name: str, traffic_mb: int, speed_limit_kbps: int? }
  Resp: { proxy: ProxyDTO, frpc_config: str, scripts: ScriptBundle }
  Err: 400 余额不足 / 端口池满 / 名称重复 / 超过最大连接数

DELETE /api/proxies/{id}
  Resp: { ok: true }

GET  /api/proxies/{id}/scripts
  Resp: { proxy: ProxyDTO, frpc_config: str, scripts: ScriptBundle }

### 管理端(需 session cookie, 登录失败返回 401)

POST /api/admin/login          Req:{username,password}  Resp:{ok:true}
POST /api/admin/logout
GET  /api/admin/proxies        Resp:{ proxies:[AdminProxyDTO,...] }
GET  /api/admin/users          Resp:{ users:[UserDTO,...] }
POST /api/admin/proxies/{id}/stop      # status -> stopped_by_admin
POST /api/admin/proxies/{id}/start     # 恢复 active
DELETE /api/admin/proxies/{id}         # 物理删除

### 聚合展示页
GET /api/show/online           Resp:{ proxies:[ShowProxyDTO,...] }
   ShowProxyDTO: { id, name, remote_port, public_url }
   public_url 形如 "http://<SERVER_PUBLIC_HOST>:<remote_port>/"

### DTO 定义

ProxyDTO = {
  id: int, name: str, token: str,
  frps_remote_port: int,
  actual_local_port: int | null,    # frps 实测, null 表示从未连接
  status: "active" | "stopped_by_admin" | "deleted",
  is_online: bool,
  speed_limit_kbps: int,
  traffic_limit_mb: int,
  traffic_used_bytes: int,
  current_speed_bps: int,
  created_at: iso8601, last_seen_at: iso8601 | null
}

AdminProxyDTO = ProxyDTO + { uid: str }
UserDTO = { uid, created_at, balance_mb, total_recharged_mb, connection_count }

ScriptBundle = {
  frpc:  { linux: str, mac: str, windows: str },   # windows 是 PowerShell
  demo:  { linux: str, mac: str, windows: str }
}
# 脚本是后端模板渲染好的成品文本, 前端直接展示/下载

## 颜色规则(前端用,后端只返回状态字段)

- 🟢 绿: 边框 #10b981 / 背景 #d1fae5  → is_online=true AND status="active"
- 🔴 红: 边框 #ef4444 / 背景 #fee2e2  → is_online=false OR 超流量
- ⚪ 灰: 边框 #9ca3af / 背景 #f3f4f6  → status="stopped_by_admin" or "deleted"

## frps Plugin 协议(后端实现, frps 调用)

frps 配置 plugin 回调地址 POST http://127.0.0.1:{BACKEND_PORT}{PLUGIN_PATH}
事件: Login / NewProxy / CloseProxy
后端按官方 frps plugin 协议返回 {reject, unchange, ...}
参考: https://github.com/fatedier/frp/blob/dev/doc/server_plugin.md

## demo 服务接口契约(C 实现, B 通过 iframe 嵌入)

demo 服务监听用户指定端口(默认 527),提供:
  GET  /                  → HTML, 留言板页面, 背景色按启动时间随机
  GET  /api/messages      → JSON [{nickname, content, timestamp}, ...]
  POST /api/messages      → Body {nickname, content}, 追加到内存

留言存内存, 进程退出即丢。HTML 页前端每 3 秒轮询 /api/messages 刷新。

## 脚本模板占位符契约(C 定义模板, A 渲染)

A 调用 C 提供的模板渲染函数(或直接读模板文件做字符串替换),占位符:
  {{SERVER_HOST}}        SERVER_PUBLIC_HOST
  {{SERVER_PORT}}        FRPS_BIND_PORT
  {{TOKEN}}              proxy.token
  {{PROXY_NAME}}         proxy.name
  {{REMOTE_PORT}}        proxy.frps_remote_port
  {{FRP_VERSION}}        FRPS_VERSION (如 v0.58.1)
  {{DEFAULT_LOCAL_PORT}} 527
  {{DEMO_BIN_BASE_URL}}  http://{SERVER_PUBLIC_HOST}:{BACKEND_PORT}/static/demo-server-bin

模板文件路径:
  scripts/frpc.linux.sh.tmpl
  scripts/frpc.mac.sh.tmpl
  scripts/frpc.win.ps1.tmpl
  scripts/demo.linux.sh.tmpl
  scripts/demo.mac.sh.tmpl
  scripts/demo.win.ps1.tmpl

## 共享 .env(三方都读同一份)

SERVER_PUBLIC_HOST=120.46.51.131
BACKEND_PORT=8000
FRPS_VERSION=v0.58.1
FRPS_BIND_PORT=7000
FRPS_ADMIN_API_URL=http://127.0.0.1:7500
FRPS_ADMIN_USER=admin
FRPS_ADMIN_PASSWORD=changeme
PLUGIN_PATH=/frps-plugin
REMOTE_PORT_RANGE_START=50000
REMOTE_PORT_RANGE_END=50100
DEFAULT_LOCAL_PORT=527
FREE_RECHARGE_AMOUNT_MB=100
DEFAULT_SPEED_LIMIT_KBPS=1024
USAGE_POLL_INTERVAL_SEC=2
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
MAX_CONNECTIONS_PER_USER=3

## 目录结构(三方共建,各自负责自己的子目录)

frps-platform/
├── .env / .env.example                  # 共享
├── backend/         (A 负责)
├── frontend/        (B 负责)
│   ├── user.html
│   ├── admin.html
│   ├── show.html
│   └── shared.css   # 颜色规则等共享样式
├── scripts/         (C 负责, 模板文件)
├── demo-server/     (C 负责, Go 兜底源码)
├── static/
│   └── demo-server-bin/   (C 产出, A 部署时静态托管)
└── frps/            (A 负责, frps 二进制和配置)

## 接口冻结说明

以上契约**冻结**,任何一方需要改动**必须在群里提出并三方同意**。
开发中如遇契约模糊,先按字面理解开发,标 TODO 后期对齐。

# 你的具体任务(C 部分)

## 范围
1. **demo 服务 Python 版** `demo-server/demo_server.py` — 留言板 HTTP 服务,内置随机背景色
2. **demo 服务 Go 兜底版** `demo-server/main.go` — 功能等价的单二进制,给没装 Python 的用户
3. **六个脚本模板** `scripts/*.tmpl` — frpc 启动 + demo 启动,各三平台
4. **预编译脚本** `demo-server/build.sh` — 一键产出 `static/demo-server-bin/` 下的三平台二进制

## 1. demo_server.py(留言板,核心彩蛋)

### 启动接口
- `python3 demo_server.py --port 527` 或 `--port` 缺省读环境变量 `PORT` 或默认 527

### HTTP 路由
- `GET /` → 返回 HTML(自包含 CSS + JS,无外部依赖)
- `GET /api/messages` → JSON `[{nickname, content, ts}, ...]`
- `POST /api/messages` → body `{nickname, content}`, 追加到内存 list, 返回 `{ok:true}`

### HTML 设计
- 标题: "留言板 #<port>"
- 留言表单: 昵称(可选,默认"匿名") + 内容(必填,限 200 字) + 提交按钮
- 留言列表: 倒序展示,每条带时间戳和昵称
- **背景色**: CSS 变量,值在进程启动时确定
  - 用 `int(time.time())` 取种子, `random.choice` 从一组**预设的好看低饱和色**里选一个
  - 预设色至少 12 个,色相分散,饱和度 30-50%,亮度 85-95%
  - 同时生成一个对比色作为强调色(标题、按钮)
- 前端 JS 每 3 秒 fetch `/api/messages` 刷新列表
- 整体风格: 干净、宽松、有点 fancy 但不土,字体用 system-ui

### 实现约束
- 只用 Python 标准库(`http.server`, `json`, `random`, `time`, `argparse`)
- 内存存储,进程退出即丢,**不写文件**
- 单文件,代码不超过 300 行
- 启动时打印一行: `留言板已启动: http://localhost:<port> (背景色: #xxxxxx)`

## 2. main.go(Go 兜底版)

### 功能要求
- 与 Python 版**功能完全一致**: 同样的路由、同样的 HTML(可以直接 embed 同一份 HTML 模板)、同样的颜色逻辑、同样的命令行 flag
- 用 Go 标准库 `net/http`, `embed`, `encoding/json`, `math/rand`, `time`, `flag`
- 单文件 `main.go`,不引外部依赖
- `go build` 直接出单二进制

### 编译脚本 build.sh
- 编译三平台:
  - `GOOS=linux GOARCH=amd64`
  - `GOOS=darwin GOARCH=amd64` 和 `GOOS=darwin GOARCH=arm64`
  - `GOOS=windows GOARCH=amd64`
- 输出到 `static/demo-server-bin/demo-server-{os}-{arch}{.exe}`

## 3. 脚本模板(六个文件)

模板占位符按共享契约,A 会负责渲染。**模板里的换行符、转义、空格必须严格正确**,A 是字符串替换,不做语法理解。

### scripts/frpc.linux.sh.tmpl(Mac 版基本一样)

```bash
#!/bin/bash
set -e

echo "=== frpc 启动脚本 ==="
read -p "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]: " PORT
PORT=${PORT:-{{DEFAULT_LOCAL_PORT}}}

ARCH=$(uname -m)
case $ARCH in
  x86_64) ARCH=amd64;;
  aarch64|arm64) ARCH=arm64;;
  *) echo "不支持的架构: $ARCH"; exit 1;;
esac

OS=linux  # mac 版改为 darwin

if [ ! -f frpc ]; then
  echo "下载 frpc {{FRP_VERSION}}..."
  curl -L -o /tmp/frp.tar.gz "https://github.com/fatedier/frp/releases/download/{{FRP_VERSION}}/frp_{{FRP_VERSION_NOV}}_${OS}_${ARCH}.tar.gz"
  tar xzf /tmp/frp.tar.gz --strip-components=1 -C /tmp/ --wildcards "*/frpc"
  mv /tmp/frpc ./frpc
  chmod +x frpc
fi

cat > frpc.toml <<EOF
serverAddr = "{{SERVER_HOST}}"
serverPort = {{SERVER_PORT}}

auth.method = "token"
auth.token = "{{TOKEN}}"

[[proxies]]
name = "{{PROXY_NAME}}"
type = "tcp"
localIP = "127.0.0.1"
localPort = ${PORT}
remotePort = {{REMOTE_PORT}}
EOF

echo "启动 frpc, 公网端口 {{REMOTE_PORT}}, 本地端口 ${PORT}"
./frpc -c frpc.toml
```

**注意**: `{{FRP_VERSION_NOV}}` 是去掉 v 前缀的版本号(如 0.58.1),A 渲染时需提供。或者只用 `{{FRP_VERSION}}` 然后在脚本里 `${VER#v}` 处理——你自己定哪种,在文档里写清楚。

### scripts/frpc.win.ps1.tmpl

```powershell
Write-Host "=== frpc 启动脚本 ==="
$portInput = Read-Host "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]"
if ([string]::IsNullOrWhiteSpace($portInput)) { $port = {{DEFAULT_LOCAL_PORT}} } else { $port = $portInput }

if (-not (Test-Path "frpc.exe")) {
    Write-Host "下载 frpc {{FRP_VERSION}}..."
    Invoke-WebRequest -Uri "https://github.com/fatedier/frp/releases/download/{{FRP_VERSION}}/frp_{{FRP_VERSION_NOV}}_windows_amd64.zip" -OutFile "frp.zip"
    Expand-Archive "frp.zip" -DestinationPath "frp_tmp"
    Copy-Item "frp_tmp\*\frpc.exe" "."
    Remove-Item -Recurse "frp_tmp", "frp.zip"
}

@"
serverAddr = "{{SERVER_HOST}}"
serverPort = {{SERVER_PORT}}

auth.method = "token"
auth.token = "{{TOKEN}}"

[[proxies]]
name = "{{PROXY_NAME}}"
type = "tcp"
localIP = "127.0.0.1"
localPort = $port
remotePort = {{REMOTE_PORT}}
"@ | Set-Content -Encoding UTF8 frpc.toml

Write-Host "启动 frpc, 公网端口 {{REMOTE_PORT}}, 本地端口 $port"
.\frpc.exe -c frpc.toml
```

### scripts/demo.linux.sh.tmpl(Mac 版基本一样)

```bash
#!/bin/bash
set -e

echo "=== Demo 留言板服务启动脚本 ==="
read -p "本地端口 [默认 {{DEFAULT_LOCAL_PORT}}]: " PORT
PORT=${PORT:-{{DEFAULT_LOCAL_PORT}}}

if command -v python3 >/dev/null 2>&1; then
    echo "使用 Python 版"
    if [ ! -f demo_server.py ]; then
        curl -L -o demo_server.py "{{DEMO_BIN_BASE_URL}}/../demo_server.py"
        # 或者 demo_server.py 由脚本内嵌, 看你选择
    fi
    python3 demo_server.py --port $PORT
else
    echo "未找到 Python, 使用内置二进制兜底"
    ARCH=$(uname -m)
    case $ARCH in x86_64) ARCH=amd64;; aarch64|arm64) ARCH=arm64;; esac
    if [ ! -f demo-server ]; then
        curl -L -o demo-server "{{DEMO_BIN_BASE_URL}}/demo-server-linux-${ARCH}"
        chmod +x demo-server
    fi
    ./demo-server --port $PORT
fi
```

### scripts/demo.win.ps1.tmpl

类似上面,先检测 `python`,无则下载 `demo-server-windows-amd64.exe`。

## 实现选择(请明确决定一种并在 README 写清)

**demo_server.py 怎么交付到用户机器上?**
- 选项 A: 脚本内嵌完整 .py 内容(用 here-doc 写出)— 优点单文件,缺点脚本会很长
- 选项 B: 脚本从后端服务器 curl 下载 — 优点脚本短,缺点多一次网络请求

**建议选 A**,脚本内嵌,体验最丝滑。Go 二进制兜底因为是二进制,必须走下载。

## 4. 测试

- `demo-server/test_demo.sh`: 启动 Python 版,curl 测三个接口
- `demo-server/test_demo_go.sh`: 编译并启动 Go 版,curl 测三个接口
- 人工 checklist: 浏览器打开 `http://localhost:527/`, 提交留言, 看到背景色随机, 多开几次进程颜色不一样

## 与 A/B 的接合点
- **不依赖 A**: 你的产物是模板和二进制,A 编译/渲染时用
- **不依赖 B**: 你的 demo 服务输出 HTML 给 iframe 嵌入,B 只是套个 iframe

## 开发期独立运行
- demo_server.py 直接 `python3 demo_server.py --port 527` 跑通
- Go 版直接 `cd demo-server && go run main.go --port 527` 跑通
- 脚本模板用一个小的渲染 demo `render_demo.py`(读模板 + 写死的假值 + 输出到 tmp/)自测

## 交付物
- demo-server/ 全部源码 + build.sh + 编译后的二进制(三平台)放到 static/demo-server-bin/
- scripts/ 六个 .tmpl 文件
- README 说明: 模板占位符列表、Python 内嵌方式还是下载方式(选 A 或 B 的决定)、Go 编译方法、人工测试 checklist
- screenshots/ 几张留言板不同背景色的截图