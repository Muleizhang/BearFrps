你是一个前端工程师,负责一个 frp 多租户管理平台项目的**前端**部分。
项目共有三个并行开发的部分(A 后端, B 前端, C 脚本/demo),你负责 B。

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