from __future__ import annotations


class PortPool:
    def __init__(self, start: int, end: int) -> None:
        if start > end:
            raise ValueError("REMOTE_PORT_RANGE_START must be <= REMOTE_PORT_RANGE_END")
        self.start = start
        self.end = end
        self._available: set[int] = set(range(start, end + 1))

    def allocate(self) -> int | None:
        if not self._available:
            return None
        port = min(self._available)
        self._available.remove(port)
        return port

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
