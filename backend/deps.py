"""@file backend/deps.py
@brief 初始化全局 Settings、端口池，并提供端口池持久化入口。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：backend.config、backend.persist_config、backend.port_pool。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和全局状态说明。
  settings：进程级只读配置对象，来源于默认值和 .env。
  port_pool：公网 TCP 端口池，管理员调整范围时会同步持久化。
  _start/_end：启动时从 config/allocatable_range.json 读取的端口边界。
  该模块导入时会创建 port_pool，因此测试需要通过 fixture 重置状态。
  端口池只管理 frps remotePort，不管理用户本机 localPort。
"""

from __future__ import annotations

from backend.config import get_settings
from backend.persist_config import load_allocatable_range, save_allocatable_range
from backend.port_pool import PortPool


settings = get_settings()
_start, _end = load_allocatable_range(
    settings.allocatable_port_range_start,
    settings.allocatable_port_range_end,
)
port_pool = PortPool(_start, _end)


def persist_port_range(start: int, end: int) -> None:
    save_allocatable_range(start, end)
