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
