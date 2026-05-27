# Demo server 与脚本模板说明

## 共享契约落地

- `GET /`：返回自包含 HTML 留言板页面。
- `GET /api/messages`：返回 `[{"nickname","content","timestamp"}, ...]`。
- `POST /api/messages`：请求体为 `{"nickname","content"}`，成功返回 `{"ok":true}`。
- 留言仅保存在内存中，进程退出后丢失。
- 页面每 3 秒轮询一次 `/api/messages`，列表按时间倒序展示。

### 字段命名决定

实现统一使用 `timestamp`，原因是共享契约前文 `SPEC/common.md:95` 已冻结为 `timestamp`。`C.md` 任务细则里出现的 `ts` 视为实现细则笔误，后续如果三方协商变更，再一起调整。

### 颜色算法契约

- 在进程启动时读取当前 Unix 秒级时间戳作为种子。
- 从固定的 12 组低饱和背景色 / 强调色配对中选 1 组。
- 选中的配色在该进程生命周期内保持不变。
- Python 版用 `random.Random(seed).choice(...)`；Go 版用同一套调色板和同样的秒级种子做一次伪随机选择。

## 脚本交付选择

选择 **B：脚本下载 `demo_server.py`**。

原因：
- `demo_server.py` 本身有单文件且不超过 300 行的硬约束，保留一份可下载源码更容易维护。
- 三个平台脚本都可以共享同一个 Python 源文件，避免内嵌副本漂移。
- 额外的一次下载只发生在本地缺少 `demo_server.py` 时，Go 兜底版本来就需要下载二进制。

Python 源文件与 Go 二进制统一放在 `static/demo-server-bin/`：
- `demo_server.py`
- `demo-server-linux-amd64`
- `demo-server-darwin-amd64`
- `demo-server-darwin-arm64`
- `demo-server-windows-amd64.exe`

## 模板占位符

脚本模板只使用共享契约中约定的占位符：

- `{{SERVER_HOST}}`
- `{{SERVER_PORT}}`
- `{{TOKEN}}`
- `{{PROXY_NAME}}`
- `{{REMOTE_PORT}}`
- `{{FRP_VERSION}}`
- `{{DEFAULT_LOCAL_PORT}}`
- `{{DEMO_BIN_BASE_URL}}`

说明：`frpc` 下载链接所需的无 `v` 版本号没有新增占位符，而是在脚本内部把 `{{FRP_VERSION}}` 做去前缀处理。

## 构建 Go 二进制

在仓库根目录执行：

```bash
./demo-server/build.sh
```

这个脚本会同时：
- 把 `demo-server/demo_server.py` 同步到 `static/demo-server-bin/demo_server.py`
- 编译 Go 兜底版到 `static/demo-server-bin/`

产物输出到：

- `static/demo-server-bin/demo_server.py`
- `static/demo-server-bin/demo-server-linux-amd64`
- `static/demo-server-bin/demo-server-darwin-amd64`
- `static/demo-server-bin/demo-server-darwin-arm64`
- `static/demo-server-bin/demo-server-windows-amd64.exe`

## 自动化自测

```bash
./demo-server/test_demo.sh
./demo-server/test_demo_go.sh
```

两个脚本都会：
- 启动对应版本服务
- curl 校验 `/`
- curl 提交一条留言
- curl 校验 `/api/messages`

## 人工验证 checklist

1. 打开 `http://localhost:527/`。
2. 检查标题为 `留言板 #527`。
3. 提交一条留言，确认列表里能看到昵称、内容、时间。
4. 刷新页面后，留言仍然存在。
5. 重启进程后，旧留言消失。
6. 多启动几次进程，确认背景色会变化。

## 手工截图建议

建议把不同背景色的浏览器截图保存到仓库外或后续新建的 `screenshots/` 目录中，至少保留 2~3 张不同配色样例用于展示。
