class Neighbor:
    def __init__(self, hardware: bytes, expires: int) -> None:
        self.hardware = hardware
        self.expires = expires


class NeighborCache:
    def __init__(self, capacity: int, lifetime_nanoseconds: int) -> None:
        self._capacity = capacity
        self._lifetime = lifetime_nanoseconds
        self._neighbors: dict[int, Neighbor] = {}

    def size(self) -> int:
        return len(self._neighbors)

    def lookup(self, address: int, now: int) -> bytes | None:
        neighbor = self._neighbors.get(address)
        if neighbor is None:
            return None
        if neighbor.expires <= now:
            del self._neighbors[address]
            return None
        return neighbor.hardware

    def learn(self, address: int, hardware: bytes, now: int) -> None:
        if address not in self._neighbors and len(self._neighbors) == self._capacity:
            self.expire(now)
        if address not in self._neighbors and len(self._neighbors) == self._capacity:
            del self._neighbors[self._soonest_to_expire()]
        self._neighbors[address] = Neighbor(hardware, now + self._lifetime)

    def forget(self, address: int) -> None:
        self._neighbors.pop(address, None)

    def expire(self, now: int) -> None:
        for address in [
            known for known in self._neighbors if self._neighbors[known].expires <= now
        ]:
            del self._neighbors[address]

    def entries(self) -> list[tuple[int, bytes]]:
        return [(address, self._neighbors[address].hardware) for address in sorted(self._neighbors)]

    def clear(self) -> None:
        self._neighbors = {}

    def _soonest_to_expire(self) -> int:
        chosen = -1
        for address in self._neighbors:
            if chosen < 0 or self._neighbors[address].expires < self._neighbors[chosen].expires:
                chosen = address
        return chosen
