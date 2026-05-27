# frp 多租户管理平台 —— 需求规格说明 v2

## 0. 项目概述

基于 frps 的多租户内网穿透自助平台,面向课堂展示。

**核心价值流:** 访问用户端 Web → 自动获得匿名 UID → 免费充值流量 → 申请连接获得 token + 公网端口 → 复制两段脚本本地运行 → 公网展示页实时显示所有人的留言板。

**部署形态:** 单台 Tencent Cloud Debian 公网服务器,跑 frps + 后端 API + 三个 Web 页面。所有可配置项集中在一个 `.env` 文件。

**展示彩蛋:** 用户本地 demo 服务端口固定为 `527`(寝室门牌号),复制下来开箱即用,改不改随意。

---

## 1. 角色与身份

### 1.1 用户(frpc 端)
- 匿名 UID(如 `u_a1b2c3d4`),首访自动生成,Cookie + localStorage 双保存
- 仅可见自己的连接和余额
- 清浏览器数据即丢身份,展示场景可接受

### 1.2 管理员
- 单一账号,用户名密码在 `.env`
- 可见全量数据,可启停/删除任意连接

### 1.3 公网展示页访客
- 无身份,只读

---

## 2. 系统组件

全部跑在同一台公网服务器同一个 Python 进程内,通过路由区分:

| 组件 | 路由 / 端口 | 说明 |
|------|-------------|------|
| frps | `:7000`(frp 控制),`:7500`(admin API,仅本机) | 官方二进制 |
| 后端 API + 三个 Web | `:8000`,路由分发 | FastAPI 单进程 |
| 用户端 Web | `/user` | |
| 管理端 Web | `/admin` | |
| 公网展示聚合页 | `/show` | |
| frps plugin 回调 | `/frps-plugin` | 内部,frps 调 |
| frps 对外代理端口池 | `50000-50100`(可配) | 分配给用户的 `remotePort` |
| 用户本地 demo 端口 | **固定 527**,用户可自改 | 不入池、不管理 |

不持久化,SQLite 用内存模式或进程重启即清空。

---

## 3. .env 配置项

```ini
# === Server ===
SERVER_PUBLIC_HOST=120.46.51.131
BACKEND_PORT=8000

# === frps ===
FRPS_VERSION=v0.58.1
FRPS_BIND_PORT=7000
FRPS_ADMIN_API_URL=http://127.0.0.1:7500
FRPS_ADMIN_USER=admin
FRPS_ADMIN_PASSWORD=changeme

# === Plugin 回调 ===
PLUGIN_PATH=/frps-plugin

# === 端口池 ===
REMOTE_PORT_RANGE_START=50000
REMOTE_PORT_RANGE_END=50100
DEFAULT_LOCAL_PORT=527            # 默认 demo 端口, 仅作为脚本里的默认值

# === 计费 ===
FREE_RECHARGE_AMOUNT_MB=100
DEFAULT_SPEED_LIMIT_KBPS=1024
USAGE_POLL_INTERVAL_SEC=2

# === 管理员 ===
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme

# === 限制 ===
MAX_CONNECTIONS_PER_USER=3
```

---

## 4. 数据模型(内存,进程退出即清)

### 4.1 User
```
uid: str
created_at: datetime
balance_mb: int
total_recharged_mb: int
```

### 4.2 Proxy
```
id: int
uid: str
name: str                        # 用户填的名字
token: str                       # 随机生成
frps_remote_port: int            # 从池里分配
status: enum                     # active / stopped_by_admin / deleted
is_online: bool                  # frps plugin 回调维护
actual_local_port: int | None    # 用户实际跑的本地端口(从 frps API 拿, 实时显示)
speed_limit_kbps: int
traffic_limit_mb: int
traffic_used_bytes: int
current_speed_bps: int
created_at: datetime
last_seen_at: datetime
```

**关键说明:** `localPort` 在脚本里固定写 527,但**用户可以自己改成任意端口**。后端不预分配、不校验本地端口,只是通过 frps admin API 把实际生效的本地端口读回来显示在面板上,让懂的人能看到"哦他改成 8080 了"。

### 4.3 留言板(核心新增)
**留言不在本平台存储**,留言数据由**每个用户自己跑的 demo 服务**持有。聚合页和留言只是把每个用户的 demo 服务展示出来。详见第 9 节和第 10 节。

### 4.4 RechargeLog
```
id, uid, amount_mb, created_at
```

---

## 5. 端口池

只管理一个池:**remote_port_pool**(公网端口)。

- 启动按 `.env` 区间初始化
- 申请时从池里取一个未占用的,绑定到 Proxy
- 删除 Proxy 释放;`stopped_by_admin` 不释放
- 池满返回明确错误

本地端口不入池,固定 527 是脚本默认值而已。

---

## 6. frps 对接

### 6.1 Server Plugin(鉴权)

frps 启动时配置 plugin,回调 `POST http://127.0.0.1:8000/frps-plugin`,处理事件:

- **Login**: 校验 token 存在、对应 Proxy 为 active、用户余额 > 0
- **NewProxy**: 校验 `remotePort` 与 token 匹配数据库记录
- **CloseProxy**: 置 `is_online=false`,记录 `last_seen_at`

### 6.2 Admin API(监控 + 踢人)

后端每 `USAGE_POLL_INTERVAL_SEC` 秒轮询 `GET /api/proxy/tcp`:

- 累计流量写入 `traffic_used_bytes`
- 差值/间隔 → `current_speed_bps`
- 从返回字段拿 `actual_local_port`(frps 知道 frpc 那边的 `localPort` 值)

**踢人逻辑(每轮询都跑):**
- 流量超额 → 调 frps admin API 删该 proxy → 状态置 `stopped_by_admin`
- 用户 `balance_mb <= 0` → 同上
- 管理员手动停 → 同上

---

## 7. 用户端 Web(`/user`)

### 7.1 顶部状态栏

- UID(可点击复制)
- 剩余流量 `XXX MB`
- 【免费充值 +100MB】按钮

### 7.2 连接列表(精简版)

每行只显示**用户真正关心**的字段:

| 名称 | 公网端口 | 本地端口 | 状态 | 已用 / 限额 | 操作 |
|------|----------|----------|------|-------------|------|

- **状态**:用整行底色 + 边框色表达
  - 🟢 绿色低饱和底色:online + active
  - 🔴 红色低饱和底色:offline 或超流量
  - ⚪ 灰色低饱和底色:被管理员禁用 / 已删除
- **本地端口**列:显示 `actual_local_port`(实时,可能是 527 也可能是用户改的),`-` 表示从未连接过
- **操作**:【查看配置/脚本】【删除】

详细字段(token、限速、瞬时速率、frps 端口) 不在主列表显示,点击行展开看详情或在【查看配置/脚本】里看。

### 7.3 申请连接表单

字段:
- 名称(必填,1-20 字符,(uid, name) 唯一)
- 分配流量 MB(必填,从余额扣)
- 限速 KB/s(可选,默认 `.env` 值)

提交 → 后端分配公网端口 + 生成 token → 弹出"配置 & 脚本"模态框。

### 7.4 配置 & 脚本模态框

三个 tab:

**Tab 1: frpc 配置文件(`frpc.toml`)**
```toml
serverAddr = "120.46.51.131"
serverPort = 7000

auth.method = "token"
auth.token = "xxxxxxxx"

[[proxies]]
name = "用户填的名字"
type = "tcp"
localIP = "127.0.0.1"
localPort = 527            # 默认 527, 改成别的也行
remotePort = 50027         # 系统分配, 别动
```

**Tab 2: 启动 frpc 脚本**(子 tab:Linux / Mac / Windows PowerShell)

逻辑:
1. 检测同目录 `frpc` / `frpc.exe`,无则下载固定版本对应平台二进制
2. 写入 `frpc.toml`(内容嵌在脚本里)
3. 启动 `./frpc -c frpc.toml`

**Tab 3: 启动 demo 服务脚本**(子 tab:Linux / Mac / Windows PowerShell)

详见第 10 节。

每个 tab 提供【复制】【下载】按钮。

### 7.5 关键接口

```
POST   /api/user/init                    # 无 UID 创建, 有则返回当前状态
POST   /api/user/recharge                # +FREE_RECHARGE_AMOUNT_MB
GET    /api/proxies                      # 我的连接列表
POST   /api/proxies                      # 申请, body: {name, traffic_mb, speed_limit_kbps}
                                         # 返回: {proxy, frpc_config, scripts: {frpc:{linux,mac,win}, demo:{linux,mac,win}}}
DELETE /api/proxies/{id}
GET    /api/proxies/{id}/scripts         # 重新拿配置和脚本
```

---

## 8. 管理端 Web(`/admin`)

### 8.1 登录

用户名密码表单,比对 `.env`,通过设 session cookie。

### 8.2 连接总览

完整字段表格(同样用整行颜色编码,规则同 7.2):

| uid | 名称 | 公网端口 | token | 本地端口 | 限速 | 已用/限额 | 当前速率 | 状态 | 操作 |

操作列:
- **停用** → status = `stopped_by_admin`,frps API 踢
- **启用** → 恢复 active(前提:余额 > 0、端口未被新人占用)
- **删除** → 物理删,释放端口

支持按 uid 筛选、按状态筛选。

### 8.3 用户列表(次要)

uid、注册时间、余额、累计充值、当前连接数。

---

## 9. 公网展示聚合页(`/show`)

**逻辑:**

- 服务端每 5 秒拉所有 `is_online=true && status=active` 的 proxy
- 渲染卡片网格,每张卡片:
  - 顶部:名称(用户起的)+ 公网端口
  - 主体:**iframe 嵌入** `http://<SERVER_PUBLIC_HOST>:<remotePort>/`
  - 底部:【直接打开 ↗】链接(fallback)
- 顶部有【刷新】按钮和"当前在线 N 个"计数

iframe 卡片本身也按颜色规则编码(理论上能渲染的都是绿)。

---

## 10. 启动脚本细节

### 10.1 demo 服务脚本(留言板版)

**功能要求:**
1. 跑一个 HTTP server 监听 527(默认)或用户输入的端口
2. 提供一个 HTML 页面,允许访客匿名留言,所有访客看到所有留言
3. 留言存内存(或同目录 `messages.json`),demo 服务进程退出即丢
4. **网页背景色根据进程启动时间生成**(种子用 `int(time.time())` 取模映射到一组好看的低饱和色,fancy 但克制)
5. 启动时**命令行交互式询问端口**(默认 527,回车采用默认)

**实现:** 用 Python 单文件 `demo_server.py` 实现 HTTP + 留言 API + HTML 渲染。脚本干两件事:
- 检查 Python 是否可用,不可用就走**内置二进制兜底**(见 10.3)
- 写出 `demo_server.py` 并启动

**`demo_server.py` 接口:**
- `GET /` → 返回 HTML 页(嵌当前所有留言、留言表单、随机背景色)
- `POST /api/messages` → body `{nickname, content}`,追加到内存列表
- `GET /api/messages` → 返回 JSON 列表(供前端轮询刷新)

HTML 页面前端简单,JS 每 3 秒轮询 `/api/messages` 刷新留言列表。背景色作为 CSS 变量,服务启动时一次性确定后不再变。

**Linux/Mac 脚本片段:**
```bash
#!/bin/bash
read -p "本地端口 [默认 527]: " PORT
PORT=${PORT:-527}

cat > demo_server.py <<'PYEOF'
# (内嵌完整的 demo_server.py 代码, 包含留言板 + 随机背景色逻辑)
PYEOF

if command -v python3 >/dev/null 2>&1; then
    python3 demo_server.py --port $PORT
else
    echo "Python3 未找到, 使用内置二进制兜底"
    # 下载或解压内置二进制版 demo server, 启动
    # (见 10.3)
fi
```

**Windows PowerShell 等价实现:** 用 `Read-Host` 拿端口,`Set-Content` 写 `demo_server.py`,`python` 启动。

### 10.2 frpc 启动脚本

**功能要求:**
1. 检测同目录 `frpc` / `frpc.exe`,无则下载固定版本对应平台二进制(固定 `FRPS_VERSION=v0.58.1`,从 GitHub releases)
2. 启动时**命令行交互式询问本地端口**(默认 527),把这个值写进 `frpc.toml` 的 `localPort`
3. 启动 `./frpc -c frpc.toml`

**Linux 示例:**
```bash
#!/bin/bash
read -p "本地端口 [默认 527]: " PORT
PORT=${PORT:-527}

ARCH=$(uname -m)
case $ARCH in
  x86_64) ARCH=amd64;;
  aarch64|arm64) ARCH=arm64;;
esac

if [ ! -f frpc ]; then
  curl -L -o frp.tar.gz "https://github.com/fatedier/frp/releases/download/v0.58.1/frp_0.58.1_linux_${ARCH}.tar.gz"
  tar xzf frp.tar.gz --strip-components=1 --wildcards "*/frpc"
  chmod +x frpc
fi

cat > frpc.toml <<EOF
serverAddr = "120.46.51.131"
serverPort = 7000

auth.method = "token"
auth.token = "xxxxxxxx"

[[proxies]]
name = "用户起的名字"
type = "tcp"
localIP = "127.0.0.1"
localPort = $PORT
remotePort = 50027
EOF

./frpc -c frpc.toml
```

Windows PowerShell 等价实现:`Read-Host` + `Invoke-WebRequest` + `Set-Content` + 启动 `frpc.exe`。

### 10.3 内置二进制兜底(demo 服务)

针对没装 Python 的用户:

- 用 Go 写一个 `demo-server` 单二进制,功能和 `demo_server.py` 完全一致(HTTP 服务 + 留言板 + 随机背景色 + `--port` flag)
- 预编译三平台版本(linux-amd64、darwin-amd64、darwin-arm64、windows-amd64.exe),放在后端服务器的 `/static/demo-server-bin/` 下
- demo 脚本检测到没 Python 时,curl/Invoke-WebRequest 下载对应平台二进制,启动

源码和 Python 版同库维护,逻辑一致,避免行为分裂。

---

## 11. UI 颜色规则(贯穿用户端 + 管理端)

所有表格行 / 卡片采用**边框色 + 低饱和背景色**编码状态:

| 状态 | 边框 | 背景 | 适用 |
|------|------|------|------|
| 🟢 online + active | `#10b981` | `#d1fae5` | 在线正常 |
| 🔴 offline / 超流量 | `#ef4444` | `#fee2e2` | 用户该跑去启动 frpc 了 |
| ⚪ stopped_by_admin / deleted | `#9ca3af` | `#f3f4f6` | 被禁用 |

具体色值前端实现时可调,核心是"绿活/红停/灰禁"三态一目了然。

---

## 12. 技术栈

- **后端:** Python 3.11+ + FastAPI + Uvicorn
- **存储:** 内存(dict + dataclass 或 pydantic 模型),进程退出即清
- **后台轮询:** asyncio 周期任务
- **前端:** 单文件 HTML + Alpine.js(轻量,够用,好看靠 Tailwind)+ Tailwind CDN
- **demo 二进制兜底:** Go 1.21+
- **frps:** v0.58.1 官方二进制

---

## 13. 目录结构建议

```
frps-platform/
├── .env
├── .env.example
├── backend/
│   ├── main.py                  # FastAPI 入口, 路由分发
│   ├── config.py                # 读 .env
│   ├── models.py                # 内存数据模型
│   ├── port_pool.py             # 端口池管理
│   ├── frps_client.py           # 调 frps admin API
│   ├── plugin_handler.py        # /frps-plugin 回调
│   ├── poller.py                # 后台轮询任务
│   ├── routes/
│   │   ├── user_api.py
│   │   ├── admin_api.py
│   │   └── show_api.py
│   └── templates/               # 三个 web 页面
│       ├── user.html
│       ├── admin.html
│       └── show.html
├── scripts/                     # 启动脚本模板
│   ├── frpc.linux.sh.tmpl
│   ├── frpc.mac.sh.tmpl
│   ├── frpc.win.ps1.tmpl
│   ├── demo.linux.sh.tmpl
│   ├── demo.mac.sh.tmpl
│   └── demo.win.ps1.tmpl
├── demo-server/                 # Go 写的兜底 demo server
│   ├── main.go
│   └── build.sh
├── static/
│   └── demo-server-bin/         # 预编译的 demo 二进制
├── frps/
│   ├── frps                     # 官方二进制
│   └── frps.toml                # 配置 plugin
└── README.md
```

---

## 14. 展示日 Checklist

- [ ] 公网服务器拉代码,跑 frps + 后端
- [ ] 端口池清空(进程重启即可)
- [ ] PPT 简要介绍页准备
- [ ] 投屏打开管理端,展示空表
- [ ] QQ 群发用户端 URL,引导:充值 → 申请 → 复制 demo 脚本跑起来 → 复制 frpc 脚本跑起来 → 双双命令行输入端口(回车默认 527)
- [ ] QQ 群发聚合页 URL,大家互相点开留言
- [ ] 投屏管理端看实时连接、流量变化、颜色变化
- [ ] PPT 详细介绍(架构、plugin 机制、踢人逻辑)
