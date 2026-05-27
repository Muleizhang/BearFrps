from __future__ import annotations

import pytest

from backend.deps import port_pool
from backend.models import store


@pytest.fixture(autouse=True)
def reset_state():
    store.reset()
    port_pool.reset()
    yield
    store.reset()
    port_pool.reset()
