from __future__ import annotations

import socket


class PortPool:
    def __init__(self, start: int, end: int) -> None:
        if start > end:
            raise ValueError("REMOTE_PORT_RANGE_START must be <= REMOTE_PORT_RANGE_END")
        self.start = start
        self.end = end
        self._available: set[int] = set(range(start, end + 1))

    def allocate(self) -> int | None:
        while self._available:
            port = min(self._available)
            self._available.remove(port)
            if not _is_port_in_use(port):
                return port
        return None

    def release(self, port: int) -> None:
        if self.start <= port <= self.end:
            self._available.add(port)

    def reserve(self, port: int) -> bool:
        if port not in self._available:
            return False
        self._available.remove(port)
        return True

    def is_port_available(self, port: int) -> bool:
        return port in self._available

    def reset(self) -> None:
        self._available = set(range(self.start, self.end + 1))

    def update_range(self, new_start: int, new_end: int,
                     currently_allocated: set[int]) -> None:
        if new_start > new_end:
            raise ValueError("start must be <= end")
        self.start = new_start
        self.end = new_end
        self._available = set(range(new_start, new_end + 1)) - currently_allocated

    def get_range(self) -> tuple[int, int]:
        return self.start, self.end

    def available_count(self) -> int:
        return len(self._available)


def _is_port_in_use(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            return False
    except OSError:
        return True
