好问题。先想清楚怎么切——并行开发的关键是**契约先行,接口冻结**,否则三个 agent 会在边界上打架。

## 切分思路

我看了一下需求,**自然的切分线是按"运行时进程"切**:

- **A. 后端 API + frps 集成**:Python 后端、端口池、frps plugin、admin API、轮询、所有 REST 接口
- **B. 三个 Web 前端**:用户端、管理端、聚合展示页(共用一套 Alpine + Tailwind 风格)
- **C. demo 服务 + 启动脚本**:`demo_server.py`、Go 兜底二进制、六个脚本模板

这三块**几乎不互相依赖代码**,只依赖契约:
- A ↔ B 通过 REST API + 颜色规则
- A ↔ C 通过脚本模板里的占位符 + frps plugin 协议
- B ↔ C 几乎无关(B 只展示 C 跑出来的 iframe)

下面三个 prompt 我每个都**先写死契约(共享部分),再写各自任务**,这样三个 agent 拿到自己的 prompt 就能独立开工,最后一拼即可。

---

## 共享契约(三个 prompt 开头都会包含这段)

````markdown
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
````

---

下面三个 prompt,每个都把上面那段共享契约包进去,然后写自己的任务。

---

## Prompt A:后端 + frps 集成

````markdown
你是一个 Python 后端工程师,负责一个 frp 多租户管理平台项目的**后端 + frps 集成**部分。
项目共有三个并行开发的部分(A 后端, B 前端, C 脚本/demo),你负责 A。

[此处插入"共享契约 v1"全文]

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
````

---

## Prompt B:三个 Web 前端

````markdown
你是一个前端工程师,负责一个 frp 多租户管理平台项目的**前端**部分。
项目共有三个并行开发的部分(A 后端, B 前端, C 脚本/demo),你负责 B。

[此处插入"共享契约 v1"全文]

# 你的具体任务(B 部分)

## 范围
做三个 HTML 单页:
1. **用户端** `frontend/user.html` — 充值、申请连接、看连接列表、看配置和脚本
2. **管理端** `frontend/admin.html` — 登录、连接总览、用户列表、启停删除
3. **公网展示聚合页** `frontend/show.html` — iframe 卡片网格,自动刷新

## 技术栈
- 单文件 HTML + Alpine.js (CDN) + Tailwind CSS (CDN)
- 无构建步骤,后端直接静态托管
- 共享样式抽到 `frontend/shared.css`(颜色变量、状态徽章、卡片样式)
- 所有 API 调用按共享契约里的 REST 定义,fetch + JSON

## 设计风格
- 干净、紧凑、信息密度高,**不要花哨**
- 状态用颜色编码(见共享契约的颜色规则),整行/整卡片应用边框色 + 低饱和背景色
- 中文 UI(展示对象是中国大学生)
- 字体: 系统默认无衬线,标题略加粗

## 页面详细

### user.html
顶部条:
- 左: 项目名 logo + slogan
- 中: UID(可点击复制,toast 提示)
- 右: 剩余流量 `XX MB` + 【免费充值 +100MB】按钮

主体:
- 【+ 申请新连接】按钮,点开模态框
- 连接列表表格(精简版):
  | 名称 | 公网端口 | 本地端口 | 状态 | 已用/限额 | 操作 |
  - 整行按状态着色
  - 本地端口列: actual_local_port 或 "-"
  - 已用/限额: 进度条 + "X / Y MB"
  - 操作: 【查看脚本】【删除】

模态框:
- 申请连接: 输入名称、流量额度(默认全部余额)、限速(可选)
- 查看脚本: 三 tab(配置文件 / frpc 脚本 / demo 脚本),每个 tab 内再分 Linux/Mac/Windows 子 tab,有【复制】【下载】按钮

页面加载:
- 调 `POST /api/user/init` 拿 UID 和余额(后端从 Cookie 取,新用户自动创建)
- 每 5 秒轮询 `GET /api/proxies` 刷新列表

### admin.html
登录页(未登录时显示):
- 简单表单,用户名密码,提交 `POST /api/admin/login`

主页(登录后):
- 顶部: "管理员控制台" + 【登出】
- Tab 切换: 连接总览 / 用户列表
- 连接总览表格(完整字段):
  | uid | 名称 | 公网端口 | token | 本地端口 | 限速 | 已用/限额 | 当前速率 | 状态 | 操作 |
  - 同样整行着色
  - 操作: 【停用】【启用】【删除】(按 status 显示不同按钮)
- 用户列表表格:
  | uid | 注册时间 | 余额 | 累计充值 | 当前连接数 |
- 上方过滤器: 按 uid 搜、按状态筛选
- 每 3 秒轮询刷新

### show.html
- 顶部: "在线服务" + 计数 + 【手动刷新】
- 主体: 卡片网格(Tailwind grid,响应式)
- 每张卡片:
  - 顶部条: 名称 + 公网端口
  - 主体: iframe `src="http://<host>:<port>/"`,固定高度 300px,可滚动
  - 底部: 【在新窗口打开 ↗】
- 每 5 秒调 `GET /api/show/online` 刷新卡片列表(diff 更新避免 iframe 闪烁)

### shared.css
```css
:root {
  --status-online-border: #10b981;
  --status-online-bg: #d1fae5;
  --status-offline-border: #ef4444;
  --status-offline-bg: #fee2e2;
  --status-disabled-border: #9ca3af;
  --status-disabled-bg: #f3f4f6;
}
.row-online { border-left: 4px solid var(--status-online-border); background: var(--status-online-bg); }
.row-offline { border-left: 4px solid var(--status-offline-border); background: var(--status-offline-bg); }
.row-disabled { border-left: 4px solid var(--status-disabled-border); background: var(--status-disabled-bg); }
/* ... */
```

提供一个 JS helper `statusClass(proxy)`,按共享契约的颜色规则返回 "row-online"/"row-offline"/"row-disabled"。

## 与 A/C 的接合点
- **依赖 A**: 调 A 的 REST API。开发期 A 可能没起,你提供一个 `mock_api.js`(本地切换,localStorage 假数据),开发时不依赖后端
- **不依赖 C**: 你只通过 iframe 展示 C 的产出,不需要 C 的源码

## 开发期独立运行
- 写一个 `dev_serve.py` 或 `python3 -m http.server` 能跑通三个页面
- mock 模式下数据用假的, 能完整走通界面交互

## 交付物
- frontend/user.html, admin.html, show.html, shared.css, mock_api.js
- 一个 screenshots/ 目录附上三个页面的截图说明
- 一份 README 说明 mock 模式怎么开关
````

---

## Prompt C:demo 服务 + 启动脚本

````markdown
你是一个全栈工程师,负责一个 frp 多租户管理平台项目的**用户本地脚本和 demo 服务**部分。
项目共有三个并行开发的部分(A 后端, B 前端, C 脚本/demo),你负责 C。

[此处插入"共享契约 v1"全文]

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
````

---

## 协作流程建议

三个 agent 拿到 prompt 后:

1. **第一轮**:三方各自跑通最小骨架,不依赖另两方的产物(用 mock 或占位)
2. **第二轮**:把产物丢到统一目录,A 加载 B 的 HTML 和 C 的模板/二进制,做集成
3. **联调**:你充当裁判,跑全链路,出问题按"谁的契约谁负责"定位

**最容易出问题的边界**:
- A 渲染脚本时占位符替换错位 → C 写模板时把所有占位符列在 README 顶部,A 拿来对照
- B 调 API 字段名拼错 → A 提供 OpenAPI doc(FastAPI 自带 `/docs`),B 直接看
- frps plugin 协议字段对不上 → 让 A 单独写一个 `plugin_handler_test.py` 用真实 frps 二进制本地起一个测一下