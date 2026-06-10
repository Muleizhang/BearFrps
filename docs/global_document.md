# BearFrps 全局完整文档

作者：BearFrps课程设计小组  
课程：武汉大学开源软件与技术课程 2026  
Git 仓库地址：<https://github.com/Muleizhang/BearFrps.git>  
许可证：Apache License 2.0  
版本：v1.0  
日期：2026-06-10

## 1. 项目概述

BearFrps 是一个基于 frp/frps 的动态连接管理平台。项目面向课堂展示场景，把 frps、后端 API、用户端、管理端和公网展示页集中到同一套服务中，解决多人同时使用 frp 时的连接申请、端口分配、配置交付、在线状态展示和管理员控制问题。

核心流程如下：

1. 用户注册或登录。
2. 用户领取演示流量。
3. 用户创建 TCP、HTTP、STCP 或 XTCP 代理。
4. 后端分配端口、生成 frpc 配置和启动脚本。
5. 用户本地运行 frpc 和 demo 留言板服务。
6. frps 插件回调后端完成认证和代理参数校验。
7. 管理端和展示页查看代理在线状态。

## 2. 功能清单

| 模块 | 功能 |
| --- | --- |
| 用户端 | 注册、登录、退出、充值、frpc token 查询与轮换、代理创建、脚本复制和下载 |
| 管理端 | 管理员登录、端口池查看与修改、代理列表、用户列表、代理启停和删除 |
| 展示页 | 聚合展示 active 且 online 的用户 demo 服务 |
| frps 插件 | 处理 Login、NewProxy、Ping、CloseProxy 事件，校验用户令牌和代理归属 |
| 轮询器 | 读取 frps admin API，更新在线状态、流量、速度和停用条件 |
| 脚本渲染 | 输出 frpc.toml、visitor 配置、Linux/macOS/Windows 启动脚本 |
| demo 服务 | 提供 Python 和 Go 两个版本的本地留言板服务 |

## 3. 系统结构

| 层次 | 主要文件 | 说明 |
| --- | --- | --- |
| 应用入口 | `backend/main.py` | 创建 FastAPI 应用，注册路由，管理启动和关闭 |
| 配置 | `backend/config.py`、`backend/deps.py` | 集中管理环境变量、端口池和共享依赖 |
| 数据模型 | `backend/models.py` | 定义 User、Proxy、TcpMapping、RechargeLog 和 Store |
| 用户 API | `backend/routes/user_api.py` | 普通用户接口 |
| 管理 API | `backend/routes/admin_api.py` | 管理员接口 |
| 展示 API | `backend/routes/show_api.py` | 展示页只读接口 |
| frps 插件 | `backend/plugin_handler.py` | frps 事件回调鉴权 |
| frps 客户端 | `backend/frps_client.py` | 访问 frps admin API |
| 流量轮询 | `backend/poller.py` | 更新在线状态和用量 |
| 脚本生成 | `backend/script_renderer.py` | 渲染 frpc 配置和启动脚本 |
| 前端 | `frontend/*.html`、`frontend/shared.css`、`frontend/mock_api.js` | 用户端、管理端、展示页和离线 mock |
| demo 服务 | `demo-server/` | 用户本地留言板服务 |
| 测试 | `tests/` | API、插件、轮询器和端口池测试 |

## 4. 关键设计

### 4.1 多租户认证

frp v0.58.1 要求 frpc 的 `auth.token` 与 frps 的 `auth.token` 匹配，因此 BearFrps 把 frps 内部认证令牌和用户级令牌分离：

- `auth.token`：frps 内部共享认证令牌。
- `metadatas.token`：用户级 frpc token。
- `metadatas.uid`：用户 uid。
- `metas.token_version`：Login 成功后由插件写入，用于令牌轮换后拒绝旧配置。

### 4.2 端口池

平台只管理 frps 的公网 `remotePort`，不管理用户机器上的 `localPort`。TCP 代理支持三种模式：

- `auto`：自动分配连续 remotePort。
- `single`：用户指定单个 remotePort。
- `range`：用户指定连续 remotePort 范围。

管理员可以调整可分配端口池。缩小端口池时，后端会拒绝会导致现有 active TCP 代理越界的配置。

### 4.3 流量和停用

轮询器定期读取 frps admin API，统计代理累计流量和当前速度。以下情况会停用代理：

- 单个代理用量达到分配流量上限。
- 用户余额小于等于 0。
- 管理员手动停用代理。

停用代理不会释放端口；删除代理才释放端口。

### 4.4 frp-Android 处理策略

`frp-Android/` 是第三方 Apache-2.0 开源移动端 frp 项目。本项目当前把它作为可后续适配的移动端组件记录在 `NOTICE` 和 `SBOM.json` 中。本次不批量修改其源码。若后续修改，应遵守以下要求：

- 保留上游 `LICENSE` 和版权声明。
- 修改过的文件使用 Doxygen 风格注释标明修改者、课程和修改内容。
- 同步更新 `NOTICE`、`SBOM.json` 和本全局文档。

## 5. API 摘要

### 5.1 用户接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/user/register` | 注册用户 |
| `POST` | `/api/user/login` | 登录用户 |
| `POST` | `/api/user/logout` | 退出登录 |
| `GET` | `/api/user/me` | 获取当前用户信息 |
| `POST` | `/api/user/recharge` | 免费充值演示流量 |
| `GET` | `/api/user/frpc-token` | 获取 frpc token |
| `POST` | `/api/user/frpc-token/rotate` | 轮换 frpc token |
| `GET` | `/api/proxies` | 获取当前用户代理 |
| `POST` | `/api/proxies` | 创建代理 |
| `GET` | `/api/proxies/{id}/scripts` | 重新获取配置和脚本 |
| `DELETE` | `/api/proxies/{id}` | 删除代理 |

### 5.2 管理和展示接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/admin/login` | 管理员登录 |
| `POST` | `/api/admin/logout` | 管理员退出 |
| `GET` | `/api/admin/config` | 获取端口池配置 |
| `POST` | `/api/admin/config` | 修改端口池配置 |
| `GET` | `/api/admin/proxies` | 获取全量代理 |
| `POST` | `/api/admin/proxies/{id}/stop` | 停用代理 |
| `POST` | `/api/admin/proxies/{id}/start` | 恢复代理 |
| `DELETE` | `/api/admin/proxies/{id}` | 删除代理 |
| `GET` | `/api/admin/users` | 获取用户列表 |
| `GET` | `/api/show/online` | 获取在线展示代理 |
| `POST` | `/frps-plugin` | frps 插件回调 |

## 6. 运行说明

### 6.1 安装依赖

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### 6.2 启动后端

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

访问地址：

- 用户端：<http://127.0.0.1:8000/user>
- 管理端：<http://127.0.0.1:8000/admin>
- 展示页：<http://127.0.0.1:8000/show>

### 6.3 启动 frps

```bash
bash frps/start.sh
```

部署前应通过 `.env` 修改默认管理员密码、frps admin 密码和内部认证 token。

## 7. 测试与质量保证

本项目要求代码可无错误运行。提交前执行：

```bash
.venv/bin/python -m pytest -q
node --check frontend/mock_api.js
python -m json.tool SBOM.json >/dev/null
.venv/bin/python tools/check_comment_ratio.py
git diff --check
```

当前验证结果：

```text
33 passed
SBOM.json ok
Comment ratio check passed
```

## 8. Doxygen 注释规范

源码注释参考 Doxygen 标记，文件头使用以下字段：

```text
@file 文件路径
@brief 文件功能摘要
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details 模块职责、依赖关系、关键业务规则和副作用
```

函数或方法注释建议使用：

```text
@brief 功能摘要
@param 参数名 参数含义、取值范围或约束
@return 返回值含义
@throws 可能抛出的异常或 HTTP 错误
@note 副作用、并发要求或安全注意事项
```

注释不应逐行翻译代码，应说明接口、约束、原因、副作用和业务规则。

## 9. 开源合规

BearFrps 根项目采用 Apache License 2.0。该许可证与 frp 和 frp-Android 的 Apache License 2.0 兼容。第三方组件记录如下：

| 组件 | 许可证 | 用途 |
| --- | --- | --- |
| frp v0.58.1 | Apache-2.0 | frps/frpc 协议和插件集成 |
| frp-Android v1.3.2 | Apache-2.0 | 可后续适配的移动端 frp 客户端 |
| FastAPI、Pydantic、pytest 等 Python 依赖 | MIT/BSD 系列 | 后端和测试 |
| Tailwind CSS、Alpine.js | MIT | 前端页面 |

完整物料清单见 `SBOM.json`，开源声明见 `NOTICE`，许可证全文见 `LICENSE`。

## 10. 口头报告与演示安排

演示目标是证明代码可运行、功能闭环完整、注释和文档符合课程要求。推荐演示顺序：

1. 展示 Git 仓库地址和 README。
2. 说明许可证、NOTICE、SBOM 和 frp/frp-Android 兼容性。
3. 运行自动化测试。
4. 启动后端并打开 `/user`。
5. 注册用户、充值、创建代理并展示生成脚本。
6. 打开管理端，展示用户、代理和端口池。
7. 打开展示页，说明在线代理过滤规则。
8. 说明 Doxygen 注释规范和 `tools/check_comment_ratio.py` 检查结果。

详细演示稿见 `docs/oral_report.md`。
