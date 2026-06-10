"""@file tests/conftest.py
@brief 为每个测试重置 Store、端口池、用户 session 和临时持久化文件。
@author BearFrps课程设计小组
@course 武汉大学开源软件与技术课程 2026
@date 2026-06-10
@version 1.0
@copyright Apache-2.0
@details
  依赖关系：pytest、backend.deps、backend.models、backend.auth。
  修改记录：2026-06-10，补充 Doxygen 风格文件头和测试隔离说明。
  每个测试使用 tmp_path 替换配置文件和用户文件路径。
  Store、端口池和 session 在测试前清空，测试后恢复初始端口范围。
  这样 API、插件和轮询器测试不会共享用户余额、代理或端口占用状态。
"""

from __future__ import annotations

import pytest

from backend.deps import port_pool
from backend.models import store
from backend.auth import clear_all_user_sessions


@pytest.fixture(autouse=True)
def reset_state(monkeypatch, tmp_path):
    from backend import persist_config, sqlite_persistence, user_persistence

    monkeypatch.setattr(persist_config, "_PERSIST_FILE", tmp_path / "allocatable_range.json")
    monkeypatch.setattr(user_persistence, "_USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(sqlite_persistence, "_DB_FILE", tmp_path / "bearfrps.db")
    _initial_range = port_pool.get_range()
    store.reset()
    clear_all_user_sessions()
    port_pool.reset()
    yield
    store.reset()
    clear_all_user_sessions()
    if port_pool.get_range() != _initial_range:
        port_pool.update_range(*_initial_range, set())
    port_pool.reset()
