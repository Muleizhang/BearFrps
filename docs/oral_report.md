# BearFrps 口头报告与演示提纲

作者：BearFrps课程设计小组  
课程：武汉大学开源软件与技术课程 2026  
Git 仓库地址：<https://github.com/Muleizhang/BearFrps.git>

## 1. 开场说明

BearFrps 是一个基于 frp 的多用户动态连接管理平台。它解决多人申请内网穿透连接时的端口冲突、配置分发、状态查看和管理员控制问题。

## 2. 演示准备

```bash
. .venv/bin/activate
.venv/bin/python -m pytest -q
node --check frontend/mock_api.js
.venv/bin/python tools/check_comment_ratio.py
./tools/generate_doxygen.sh
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开：

- 用户端：<http://127.0.0.1:8000/user>
- 管理端：<http://127.0.0.1:8000/admin>
- 展示页：<http://127.0.0.1:8000/show>

## 3. 演示步骤

1. 展示 README、全局文档、LICENSE、NOTICE、SBOM。
2. 说明 Apache-2.0 许可证选择及其与 frp/frp-Android 的兼容性。
3. 运行自动化测试和注释比例检查。
4. 用户端注册账号并领取流量。
5. 创建一个 TCP 代理，展示 remotePort、localPort、frpc 配置和启动脚本。
6. 轮换 frpc token，说明旧配置会被插件拒绝。
7. 管理端查看代理和用户，演示停用或删除代理。
8. 展示页说明 active 且 online 的代理过滤规则。
9. 展示 Doxygen 风格文件头、注释比例检查脚本和生成的 HTML 文档。

## 4. 讲解要点

- `auth.token` 是 frps 内部令牌，`metadatas.token` 是用户级令牌。
- 平台分配公网 `remotePort`，用户本地 `localPort` 可按实际服务调整。
- 端口池支持自动、单端口和连续范围三种模式。
- 管理员停用代理会保留端口，删除代理时释放端口。
- `frp-Android/` 是 Apache-2.0 第三方项目，移动端适配时保留许可和修改记录。
- 注释采用 Doxygen 风格，包含 `@file`、`@brief`、`@author`、`@course`、`@details` 等字段。
