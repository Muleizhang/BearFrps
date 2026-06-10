"""@file backend/__init__.py
@brief 声明后端包边界，便于 FastAPI、测试和脚本以包方式导入业务模块。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：无直接运行时依赖。
  修改记录：2026-06-10，补充 Doxygen 风格文件头。
  后端包包含配置、认证、数据模型、frps 插件、轮询器、脚本渲染和 API 路由。
  该文件不执行副作用代码，避免导入 backend 时隐式启动 frps 或创建网络连接。
  所有实际初始化由 backend.main 的 FastAPI lifespan 统一管理。
  测试中通过包导入复用同一份模块状态，因此这里保持最小化。
"""
