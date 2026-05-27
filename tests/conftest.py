from __future__ import annotations

import pytest

from backend.config import ROOT_DIR
from backend.deps import port_pool
from backend.models import store

_PERSIST_FILE = ROOT_DIR / "config" / "allocatable_range.json"


@pytest.fixture(autouse=True)
def reset_state():
    if _PERSIST_FILE.exists():
        _PERSIST_FILE.unlink()
    _initial_range = port_pool.get_range()
    store.reset()
    port_pool.reset()
    yield
    store.reset()
    if port_pool.get_range() != _initial_range:
        port_pool.update_range(*_initial_range, set())
    port_pool.reset()
