from __future__ import annotations

from backend.config import get_settings
from backend.port_pool import PortPool


settings = get_settings()
port_pool = PortPool(settings.remote_port_range_start, settings.remote_port_range_end)
