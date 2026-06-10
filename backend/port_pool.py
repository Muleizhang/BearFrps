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
        ports = self.allocate_contiguous(1)
        return ports[0] if ports else None

    def allocate_contiguous(self, count: int) -> list[int] | None:
        if count <= 0:
            return None
        for start in range(self.start, self.end - count + 2):
            ports = list(range(start, start + count))
            if not all(port in self._available for port in ports):
                continue
            system_in_use = [port for port in ports if _is_port_in_use(port)]
            if system_in_use:
                for port in system_in_use:
                    self._available.discard(port)
                continue
            for port in ports:
                self._available.remove(port)
            return ports
        return None

    def release(self, port: int) -> None:
        if self.start <= port <= self.end:
            self._available.add(port)

    def release_many(self, ports: list[int] | tuple[int, ...] | set[int]) -> None:
        for port in ports:
            self.release(port)

    def reserve(self, port: int) -> bool:
        unavailable = self.reserve_many([port])
        return not unavailable

    def reserve_many(self, ports: list[int] | tuple[int, ...] | set[int]) -> list[int]:
        requested = list(dict.fromkeys(ports))
        unavailable = self.unavailable_ports(requested)
        if unavailable:
            return unavailable
        for port in requested:
            self._available.remove(port)
        return []

    def unavailable_ports(self, ports: list[int] | tuple[int, ...] | set[int]) -> list[int]:
        unavailable: list[int] = []
        for port in dict.fromkeys(ports):
            if port < self.start or port > self.end:
                unavailable.append(port)
            elif port not in self._available:
                unavailable.append(port)
            elif _is_port_in_use(port):
                unavailable.append(port)
        return unavailable

    def is_port_available(self, port: int) -> bool:
        if port < self.start or port > self.end:
            return False
        return port in self._available and not _is_port_in_use(port)

    def is_port_unreserved(self, port: int) -> bool:
        return self.start <= port <= self.end and port in self._available

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
