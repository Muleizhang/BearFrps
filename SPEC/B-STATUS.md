# B 前端交付状态 — ABC 三方对齐文档

> 本文档供 A（后端）、C（脚本/demo）开发者阅读，快速了解 B 前端已做了什么、与你方的接合点在哪、需要你方怎么配合。

---

## 1. B 已交付文件清单

```
frontend/
├── user.html        # 用户端单页（305 行）
├── admin.html       # 管理端单页（258 行）
├── show.html        # 公网展示聚合页（96 行）
├── shared.css       # 共享样式（231 行）：CSS 变量、状态行/卡片/徽章/按钮/模态框/进度条/toast
├── mock_api.js      # Mock API 层（439 行）：拦截 fetch，localStorage 假数据，含全局 helper 函数
└── dev_serve.py     # 开发用 HTTP server（37 行）：python3 dev_serve.py 即可跑
```

开发期可完全脱离 A、C 独立运行，所有 API 都有 mock。

---

## 2. B 前端实际调用的全部 API（按页面分组）

### 2.1 user.html 调用

| 时机 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 页面加载 | POST | `/api/user/init` | 拿 uid + 余额，body `{}` |
| 用户点击 | POST | `/api/user/recharge` | 免费充值，body `{}` |
| 每 5 秒 | GET | `/api/proxies` | 刷新连接列表 |
| 用户提交 | POST | `/api/proxies` | 申请连接，body `{ name, traffic_mb, speed_limit_kbps? }` |
| 用户点击 | GET | `/api/proxies/{id}/scripts` | 获取配置+脚本 |
| 用户点击 | DELETE | `/api/proxies/{id}` | 删除连接 |

### 2.2 admin.html 调用

| 时机 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 登录 | POST | `/api/admin/login` | body `{ username, password }` |
| 登出 | POST | `/api/admin/logout` | |
| 每 3 秒 | GET | `/api/admin/proxies` | 连接总览 |
| 每 3 秒 | GET | `/api/admin/users` | 用户列表 |
| 管理员点击 | POST | `/api/admin/proxies/{id}/stop` | 停用 |
| 管理员点击 | POST | `/api/admin/proxies/{id}/start` | 启用 |
| 管理员点击 | DELETE | `/api/admin/proxies/{id}` | 删除 |

### 2.3 show.html 调用

| 时机 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 每 5 秒 | GET | `/api/show/online` | 在线 proxy 列表 |

---

## 3. B 前端对响应格式的严格要求（对 A）

B 前端严格按 SPEC/B.md 的 DTO 定义消费 JSON。以下是 B 实际用到的字段：

### 3.1 POST `/api/user/init` 响应

```json
{ "uid": "u_a1b2c3d4", "balance_mb": 100, "total_recharged_mb": 100, "created_at": "..." }
```

B 用到：`uid`（显示 + 复制）、`balance_mb`（显示）、`total_recharged_mb`（充值后更新）

### 3.2 POST `/api/user/recharge` 响应

```json
{ "balance_mb": 200, "total_recharged_mb": 200 }
```

### 3.3 GET `/api/proxies` 响应

```json
{ "proxies": [ProxyDTO, ...] }
```

B 用到 ProxyDTO 的以下字段：

| 字段 | 用途 |
|------|------|
| `id` | key、DELETE/GET 路径参数 |
| `name` | 表格显示 |
| `frps_remote_port` | 表格"公网端口"列 |
| `actual_local_port` | 表格"本地端口"列，null 显示 "-" |
| `status` | 颜色判断 (`active` / `stopped_by_admin` / `deleted`) |
| `is_online` | 颜色判断 |
| `traffic_used_bytes` | 进度条计算 |
| `traffic_limit_mb` | 进度条 + "已用/限额"文字 |
| `current_speed_bps` | （user 页未显示，但 mock 里维护了） |

### 3.4 POST `/api/proxies` 请求 & 响应

**请求：**
```json
{ "name": "xxx", "traffic_mb": 50, "speed_limit_kbps": 1024 }
```

**响应（200 OK）：**
```json
{
  "proxy": { ProxyDTO },
  "frpc_config": "serverAddr = ...（完整 toml 字符串）",
  "scripts": {
    "frpc":  { "linux": "...", "mac": "...", "windows": "..." },
    "demo":  { "linux": "...", "mac": "...", "windows": "..." }
  }
}
```

**B 对 `scripts` 的消费方式：**
- `frpc_config` 放在"配置文件" tab
- `scripts.frpc.linux/mac/windows` 放在"frpc 启动脚本" tab
- `scripts.demo.linux/mac/windows` 放在"demo 启动脚本" tab
- 每个 tab 有【复制】和【下载】按钮，内容是**后端返回的纯文本**，前端直接展示

**B 期望的错误响应（400）：**
```json
{ "detail": "余额不足" }
```
前端会把 `detail` 字符串直接显示为错误提示。请确保所有 400 返回都有 `detail` 字段。

### 3.5 GET `/api/proxies/{id}/scripts` 响应

格式同 POST `/api/proxies` 的 200 响应。

### 3.6 管理端接口

**GET `/api/admin/proxies`：**
```json
{ "proxies": [AdminProxyDTO, ...] }
```

AdminProxyDTO = ProxyDTO + `uid` 字段。B 在 admin 表格里额外显示了 `uid`、`token`、`speed_limit_kbps`、`current_speed_bps`。

**GET `/api/admin/users`：**
```json
{ "users": [{ "uid", "created_at", "balance_mb", "total_recharged_mb", "connection_count" }, ...] }
```

**管理端操作接口（stop/start/delete）：**成功返回 `{ "ok": true }`，失败返回 401 或 404 `{ "detail": "..." }`。

### 3.7 GET `/api/show/online` 响应

```json
{
  "proxies": [
    { "id": 1, "name": "xxx", "remote_port": 50001, "public_url": "http://120.46.51.131:50001/" }
  ]
}
```

B 用 `public_url` 作为 iframe 的 `src` 和"新窗口打开"链接的 `href`。用 `id` 做 diff 判断避免 iframe 闪烁。

---

## 4. B 对 A 的具体要求清单

### 4.1 Cookie / Session 行为

- **用户端**：B 调 `POST /api/user/init`，A 从 Cookie 取 `uid`，不存在则创建并 Set-Cookie。B 不自行管理 Cookie。
- **管理端**：B 调 `POST /api/admin/login` 后，A 用 session cookie 标识登录态。B 后续请求浏览器自动带 cookie。401 时 B 自动跳回登录页。

### 4.2 静态文件托管

A（FastAPI）需要托管 B 的三个 HTML + CSS 文件，路由规则：

| 路由 | 文件 |
|------|------|
| `/user` | `frontend/user.html` |
| `/admin` | `frontend/admin.html` |
| `/show` | `frontend/show.html` |
| `/frontend/shared.css` | `frontend/shared.css`（三个 HTML 的 `<link>` 引用路径） |
| `/frontend/mock_api.js` | `frontend/mock_api.js`（三个 HTML 的 `<script>` 引用路径） |

**注意：** 三个 HTML 里的引用路径是相对路径 `shared.css` 和 `mock_api.js`（同目录），如果 A 部署时改了路径，需要同步修改 HTML 中的 href/src。

**生产环境：** 把 `mock_api.js` 的 `<script>` 标签删掉，或将 `mock_api.js` 中的 `window.USE_MOCK = true` 改为 `false`。mock_api.js 里除了 mock 逻辑外还注册了一些全局 helper 函数（`statusClass`、`statusBadge`、`copyText`、`downloadText`、`formatBytes`、`formatSpeed`、`toast`），如果删掉 mock_api.js，需要把这些 helper 搬到别处或内联到各 HTML。

**推荐做法：** A 部署时保留 mock_api.js 文件，仅把第一行 `window.USE_MOCK = true` 改为 `window.USE_MOCK = false`。这样所有全局 helper 函数仍然可用，但 fetch 不再被拦截，请求直达后端。

### 4.3 跨域

三个页面由 A 的 FastAPI 同源托管，不存在跨域问题。API 和页面都在同一个 `:8000` 端口。

---

## 5. B 对 C 的关系

B 与 C **无直接依赖**。交互方式：

1. show.html 通过 `public_url`（形如 `http://120.46.51.131:50001/`）用 `<iframe>` 嵌入用户跑起来的 demo 服务
2. iframe 使用 `sandbox="allow-scripts allow-same-origin allow-forms"` 属性
3. 如果用户还没跑 demo 服务，iframe 会显示无法连接，这是预期行为
4. show.html 里有"在新窗口打开"链接作为 fallback

C 不需要为 B 做任何适配。只要 demo 服务实现了共享契约里的三个接口（`GET /`、`GET /api/messages`、`POST /api/messages`），iframe 就能正常显示留言板。

---

## 6. B 前端中的状态颜色判断逻辑

B 在 mock_api.js 中定义了全局函数 `statusClass(proxy)` 和 `statusBadge(proxy)`，逻辑如下：

```
if status == "stopped_by_admin" or "deleted" → 灰色（row-disabled）
if is_online == false                        → 红色（row-offline）
if traffic_used >= traffic_limit              → 红色（row-offline）
otherwise                                     → 绿色（row-online）
```

优先级：灰 > 红 > 绿。即 stopped/deleted 永远灰色，不管 online 状态。

这三个状态判断**完全在前端**，A 只需要返回 `status`、`is_online`、`traffic_used_bytes`、`traffic_limit_mb` 这几个字段，不需要做颜色判断。

---

## 7. B 前端中的进度条计算

```javascript
percent = (traffic_used_bytes / (traffic_limit_mb * 1024 * 1024)) * 100
```

进度条颜色：
- percent <= 70：绿色（fill-ok）
- 70 < percent <= 90：黄色（fill-warn）
- percent > 90：红色（fill-danger）

所以 `traffic_used_bytes` 的单位是**字节**，`traffic_limit_mb` 的单位是**MB**。请确保单位一致。

---

## 8. B 前端中的格式化函数

mock_api.js 中注册了全局函数，B 的 HTML 模板里直接调用：

| 函数 | 用途 | 示例输出 |
|------|------|----------|
| `formatBytes(bytes)` | 流量显示 | `"1.5 MB"`、`"256.0 KB"` |
| `formatSpeed(bps)` | 速率显示 | `"128.0 KB/s"` |
| `copyText(text)` | 复制到剪贴板 + toast 提示 | |
| `downloadText(text, filename)` | 下载文本文件 | |
| `toast(msg)` | 底部弹窗 2 秒消失 | |

---

## 9. 对接检查清单

### A（后端）需要确认：

- [ ] 所有 15 个 API 端点已实现，路径和 B 调用的一致
- [ ] POST `/api/user/init` 从 Cookie 取/创建 uid，返回格式正确
- [ ] POST `/api/proxies` 返回 `{ proxy, frpc_config, scripts }` 格式正确
- [ ] GET `/api/proxies/{id}/scripts` 返回格式正确
- [ ] `scripts` 是 ScriptBundle 结构（6 个字符串，已渲染好的成品脚本）
- [ ] `traffic_used_bytes` 单位是字节（不是 MB）
- [ ] `traffic_limit_mb` 单位是 MB（不是字节）
- [ ] `actual_local_port` 类型是 `int | null`（不是字符串）
- [ ] 400 错误响应有 `detail` 字段
- [ ] 401 错误响应有 `detail` 字段
- [ ] `/user`、`/admin`、`/show` 三个路由能正确返回对应 HTML 文件
- [ ] `frontend/` 目录下的 CSS/JS 文件能被正确引用

### C（脚本/demo）需要确认：

- [ ] demo 服务实现了 `GET /`、`GET /api/messages`、`POST /api/messages`
- [ ] `GET /` 返回完整 HTML 页面（留言板 + 3 秒自动刷新）
- [ ] demo 服务能通过 frpc 的 remote_port 从公网访问
- [ ] 脚本模板文件放在 `scripts/` 目录，文件名和占位符符合共享契约
- [ ] Go 兜底二进制放在 `static/demo-server-bin/`

---

## 10. mock_api.js 中的全局函数（生产环境需保留）

即使 `USE_MOCK = false`，以下全局函数仍被三个 HTML 使用。A 部署时**不能直接删除 mock_api.js**，只能改 `USE_MOCK` 开关：

| 全局变量/函数 | 使用页面 |
|---------------|----------|
| `statusClass(proxy)` | user.html、admin.html |
| `statusBadge(proxy)` | user.html、admin.html |
| `cardStatusClass(proxy)` | show.html（已定义但未使用，预留） |
| `toast(msg)` | 三个页面都用 |
| `copyText(text)` | user.html（复制 UID） |
| `downloadText(text, filename)` | user.html（下载脚本） |
| `formatBytes(bytes)` | user.html、admin.html |
| `formatSpeed(bps)` | admin.html |

---

## 11. 已知限制 / TODO

1. **mock_api.js 中的脚本内容**是 B 前端自行硬编码的简化版，不是 C 的正式模板。正式环境的脚本内容完全由 A 后端从 C 的模板渲染返回，B 前端只是展示容器。
2. **mock 模式下 show.html 的 iframe** 会加载失败（没有真实的 demo 服务），这是预期行为。
3. **admin.html 的删除按钮**在 `active` 和 `stopped_by_admin` 状态都显示（不区分），符合 SPEC 要求。
4. **user.html 的脚本模态框**里 `createResult` 是从父 scope 传入 `x-data="{ mt, st }"` 子 scope 的，依赖 Alpine.js 的 scope chain，已验证可行。
