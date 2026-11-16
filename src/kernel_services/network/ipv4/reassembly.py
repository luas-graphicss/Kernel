from kernel_services.network.counters import (
    DATAGRAMS_REASSEMBLED,
    FRAGMENTS_EVICTED,
    FRAGMENTS_EXPIRED,
    FRAGMENTS_INVALID,
    FRAGMENTS_RECEIVED,
    Counters,
)
from kernel_services.network.ipv4.header import (
    HEADER_BYTES,
    MAXIMUM_DATAGRAM_BYTES,
    OFFSET_UNIT_BYTES,
    Datagram,
)

UNKNOWN_LENGTH = -1
MAXIMUM_PAYLOAD_BYTES = MAXIMUM_DATAGRAM_BYTES - HEADER_BYTES
PLACED = 0
DUPLICATE = 1
CONFLICTING = 2


class Assembly:
    def __init__(self, created: int) -> None:
        self.created = created
        self.pieces: list[tuple[int, bytes]] = []
        self.held_bytes = 0
        self.total_bytes = UNKNOWN_LENGTH

    def place(self, offset: int, data: bytes, is_last: bool) -> int:
        end = offset + len(data)
        if not self._agrees_on_length(end, is_last):
            return CONFLICTING
        position = 0
        for start, piece in self.pieces:
            if start == offset and piece == data:
                return DUPLICATE
            if offset < start + len(piece) and start < end:
                return CONFLICTING
            if start < offset:
                position += 1
        if is_last:
            self.total_bytes = end
        self.pieces.insert(position, (offset, data))
        self.held_bytes += len(data)
        return PLACED

    def joined(self) -> bytes | None:
        if self.total_bytes == UNKNOWN_LENGTH:
            return None
        expected = 0
        for start, piece in self.pieces:
            if start != expected:
                return None
            expected += len(piece)
        if expected != self.total_bytes:
            return None
        return b"".join([piece for _start, piece in self.pieces])

    def _agrees_on_length(self, end: int, is_last: bool) -> bool:
        if self.total_bytes != UNKNOWN_LENGTH:
            return end <= self.total_bytes and not (is_last and end != self.total_bytes)
        if not is_last:
            return True
        return all(start + len(piece) <= end for start, piece in self.pieces)


class Reassembler:
    def __init__(
        self, max_datagrams: int, max_bytes: int, lifetime_nanoseconds: int, counters: Counters
    ) -> None:
        self._max_datagrams = max_datagrams
        self._max_bytes = max_bytes
        self._lifetime = lifetime_nanoseconds
        self._counters = counters
        self._assemblies: dict[tuple[int, int, int, int], Assembly] = {}
        self._held_bytes = 0

    def pending(self) -> int:
        return len(self._assemblies)

    def held_bytes(self) -> int:
        return self._held_bytes

    def add(self, fragment: Datagram, now: int) -> bytes | None:
        self._counters.count(FRAGMENTS_RECEIVED)
        key = (fragment.source, fragment.destination, fragment.protocol, fragment.identification)
        data = fragment.payload
        offset = fragment.fragment_offset()
        is_last = not fragment.has_more_fragments()
        if not self._is_well_formed(offset, data, is_last):
            self._invalidate(key)
            return None
        assembly = self._assemblies.get(key)
        if assembly is None:
            assembly = self._admit(key, now)
        if not self._make_room(key, len(data)):
            self._invalidate(key)
            return None
        placement = assembly.place(offset, data, is_last)
        if placement == CONFLICTING:
            self._invalidate(key)
            return None
        if placement == PLACED:
            self._held_bytes += len(data)
        payload = assembly.joined()
        if payload is not None:
            self._drop(key)
            self._counters.count(DATAGRAMS_REASSEMBLED)
        return payload

    def expire(self, now: int) -> None:
        for key in [held for held in self._assemblies if self._expires(held) <= now]:
            self._drop(key)
            self._counters.count(FRAGMENTS_EXPIRED)

    def next_deadline(self, none: int) -> int:
        deadline = none
        for key in self._assemblies:
            if self._expires(key) < deadline:
                deadline = self._expires(key)
        return deadline

    def _expires(self, key: tuple[int, int, int, int]) -> int:
        return self._assemblies[key].created + self._lifetime

    def _is_well_formed(self, offset: int, data: bytes, is_last: bool) -> bool:
        if len(data) == 0 or offset + len(data) > MAXIMUM_PAYLOAD_BYTES:
            return False
        return is_last or len(data) % OFFSET_UNIT_BYTES == 0

    def _admit(self, key: tuple[int, int, int, int], now: int) -> Assembly:
        if len(self._assemblies) == self._max_datagrams:
            self._evict_oldest(key)
        assembly = Assembly(now)
        self._assemblies[key] = assembly
        return assembly

    def _make_room(self, key: tuple[int, int, int, int], needed: int) -> bool:
        while self._held_bytes + needed > self._max_bytes:
            if not self._evict_oldest(key):
                return False
        return True

    def _evict_oldest(self, kept: tuple[int, int, int, int]) -> bool:
        oldest = None
        for key in self._assemblies:
            if key == kept:
                continue
            if oldest is None or self._assemblies[key].created < self._assemblies[oldest].created:
                oldest = key
        if oldest is None:
            return False
        self._drop(oldest)
        self._counters.count(FRAGMENTS_EVICTED)
        return True

    def _invalidate(self, key: tuple[int, int, int, int]) -> None:
        self._drop(key)
        self._counters.count(FRAGMENTS_INVALID)

    def _drop(self, key: tuple[int, int, int, int]) -> None:
        assembly = self._assemblies.pop(key, None)
        if assembly is not None:
            self._held_bytes -= assembly.held_bytes
