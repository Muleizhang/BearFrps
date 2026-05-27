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