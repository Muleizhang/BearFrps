你是一个 Python 后端工程师,负责一个 frp 多租户管理平台项目的**后端 + frps 集成**部分。
项目共有三个并行开发的部分(A 后端, B 前端, C 脚本/demo),你负责 A。

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
# 你的具体任务(A 部分)

## 范围
1. 用 FastAPI 实现共享契约里的所有 `/api/*` 接口和 `/frps-plugin` 回调
2. 实现端口池管理、内存数据模型、frps admin API 客户端、后台轮询任务、踢人逻辑
3. 配置并管理 frps 进程(写 `frps/frps.toml`,提供启动脚本)
4. 静态托管前端 HTML(B 产出)和 demo 二进制(C 产出)

## 技术栈
- Python 3.11+, FastAPI, Uvicorn, httpx, pydantic v2, python-dotenv
- 内存存储(dict + pydantic model),不用数据库,进程重启清空
- 后台任务用 asyncio + `asyncio.create_task` 周期循环

## 目录结构(你负责的部分)

backend/
├── main.py                  # FastAPI 入口, lifespan 里启 frps 子进程和轮询任务
├── config.py                # 读 .env, 单例 Settings
├── models.py                # User, Proxy, RechargeLog 内存模型 + 全局 Store
├── port_pool.py             # 公网端口池, 分配/释放/查询
├── frps_client.py           # 调 frps admin API: 获取 proxy 列表/流量, 踢 proxy
├── plugin_handler.py        # /frps-plugin 回调路由, Login/NewProxy/CloseProxy
├── poller.py                # 后台任务: 轮询 frps API, 更新流量, 触发踢人
├── script_renderer.py       # 读 scripts/*.tmpl, 用占位符渲染成成品文本
├── routes/
│   ├── user_api.py          # /api/user/*, /api/proxies*
│   ├── admin_api.py         # /api/admin/*  + session 中间件
│   └── show_api.py          # /api/show/online
└── auth.py                  # 用户 UID Cookie 中间件, 管理员 session

frps/
├── frps                     # 官方二进制 v0.58.1, 启动脚本下载
├── frps.toml                # plugin 配置模板, 启动时根据 .env 渲染
└── start.sh                 # 下载+启动 frps

## 关键实现要点

### 端口池
- 启动时按 .env 区间生成可用集合 `set(range(start, end+1))`
- 分配: pop 最小值; 释放: add 回去
- 提供 `is_port_available(p)` 给 plugin 校验用

### 数据模型(内存)
- `Store` 单例: `users: dict[uid -> User]`, `proxies: dict[id -> Proxy]`, `proxy_id_counter: int`
- 用 asyncio.Lock 保护并发改写
- 提供 `find_proxy_by_token(token)`, `find_proxy_by_remote_port(port)` 等查询

### frps_client.py
- 用 httpx.AsyncClient, basic auth 用 FRPS_ADMIN_USER/PASSWORD
- 方法:
  - `async def list_tcp_proxies() -> list[dict]`  # GET /api/proxy/tcp
  - `async def get_proxy_traffic(name) -> dict`   # 累计流量
  - `async def kick_proxy(name)`                   # DELETE 不可达, 改为标记 proxy disabled, 实测中发现 frps 没有直接 kick 单个 proxy 的 API; 替代方案: 通过 plugin Login 时拒绝, 配合内存里把 status 改成 stopped, 等下次心跳超时
  - **注意**: frps admin API 能查不能强制 kick。踢人靠两步: 1) 内存 status 改 stopped, 2) frpc 重连时 plugin Login 返回 reject。已连接的会话需要等心跳超时(可在 frps.toml 里设小一点 heartbeatTimeout)

### plugin_handler.py
- 严格按 frps server plugin 协议: 收到 `{version, op, content}`, 返回 `{reject:bool, reject_reason:str, unchange:bool, content:object}`
- Login op: 从 content.metas 或 content.user 拿 token, 查 Proxy, 校验 status==active 且 balance>0
- NewProxy op: 校验 remotePort 在池内且属于这个 token 对应的 Proxy
- CloseProxy op: 置 is_online=false

### poller.py
- 每 USAGE_POLL_INTERVAL_SEC 秒一轮:
  1. 调 frps_client.list_tcp_proxies(),拿到 name -> {today_traffic_in/out, last_start_time, cur_conns, ...}
  2. 对每个 active proxy:
     - 累计流量写入 traffic_used_bytes(注意 frps 返回的是 today 流量, 你要算增量)
     - 算当前速率: (本轮总量 - 上轮总量) / interval
     - 从 frps 返回里能拿到 frpc 那侧的 client info, 记录 actual_local_port
     - is_online = (name 在返回里)
  3. 踢人检查:
     - traffic_used_bytes >= traffic_limit_mb*1MB → status=stopped_by_admin
     - balance_mb <= 0 → 同上
     - 同时从用户余额扣减本轮增量

### script_renderer.py
- 启动时读取 scripts/*.tmpl 缓存到内存
- `render_bundle(proxy, settings) -> ScriptBundle`: 对六个模板做字符串替换
- 模板由 C 提供, 你只负责读和渲染

### main.py lifespan
- 启动: 读 .env → 初始化 Store/PortPool → 渲染并写 frps.toml → 启 frps 子进程 → 启 poller → 启 FastAPI
- 关闭: 停 poller, kill frps 子进程

### 路由挂载
- `/api/user/*`, `/api/proxies*`, `/api/admin/*`, `/api/show/*`, `/frps-plugin`
- `/user`, `/admin`, `/show` → 返回对应的 frontend/*.html(B 产出)
- `/static/*` → StaticFiles 挂 static/ 目录

### 测试
- 提供 `tests/test_api.py`, 用 TestClient 跑通主流程: init → recharge → create proxy → list → delete
- 提供 `tests/test_plugin.py`, mock frps 回调
- 提供 README,说明如何独立启动后端(不依赖 B 和 C 的产物,缺失时用 placeholder)

## 与 B/C 的接合点
- **不依赖 B**: B 没产出时, /user /admin /show 返回 "frontend not ready" 占位 HTML
- **不依赖 C**: C 没产出时, script_renderer 检测不到 .tmpl 就返回 "# template not ready" 字符串; demo-server-bin/ 目录可以为空

## 交付物
- 完整 backend/ 代码
- frps/ 配置和启动脚本
- README.md(怎么跑、怎么测、配置项说明)
- requirements.txt