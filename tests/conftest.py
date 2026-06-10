from __future__ import annotations

import pytest

from backend.deps import port_pool
from backend.models import store
from backend.auth import clear_all_user_sessions


@pytest.fixture(autouse=True)
def reset_state(monkeypatch, tmp_path):
    from backend import persist_config, user_persistence

    monkeypatch.setattr(persist_config, "_PERSIST_FILE", tmp_path / "allocatable_range.json")
    monkeypatch.setattr(user_persistence, "_USERS_FILE", tmp_path / "users.json")
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
