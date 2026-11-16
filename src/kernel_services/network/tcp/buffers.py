from kernel_services.network.tcp.sequence import HALF, advance, distance


class ByteQueue:
    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._consumed = 0
        self.size = 0

    def append(self, data: bytes) -> None:
        if data:
            self._chunks.append(data)
            self.size += len(data)

    def peek(self, offset: int, length: int) -> bytes:
        position = offset + self._consumed
        parts = []
        for chunk in self._chunks:
            if length == 0:
                break
            if position >= len(chunk):
                position -= len(chunk)
                continue
            part = chunk[position : position + length]
            parts.append(part)
            length -= len(part)
            position = 0
        if len(parts) == 1:
            return parts[0]
        return b"".join(parts)

    def discard(self, count: int) -> None:
        self.size -= count
        count += self._consumed
        while self._chunks and count >= len(self._chunks[0]):
            count -= len(self._chunks.pop(0))
        self._consumed = count

    def take(self, count: int) -> bytes:
        taken = self.peek(0, count)
        self.discard(len(taken))
        return taken

    def clear(self) -> None:
        self._chunks = []
        self._consumed = 0
        self.size = 0


class OutOfOrderQueue:
    def __init__(self, max_segments: int) -> None:
        self._max_segments = max_segments
        self._segments: list[tuple[int, bytes]] = []
        self.held_bytes = 0

    def count(self) -> int:
        return len(self._segments)

    def insert(self, expected: int, sequence: int, data: bytes) -> bool:
        start = distance(sequence, expected)
        index = 0
        while index < len(self._segments) and data:
            held_sequence, held = self._segments[index]
            held_start = distance(held_sequence, expected)
            held_end = held_start + len(held)
            if held_end <= start:
                index += 1
                continue
            if held_start >= start + len(data):
                break
            if held_start > start:
                if not self._put(index, advance(expected, start), data[: held_start - start]):
                    return False
                index += 1
            data = data[held_end - start :] if held_end < start + len(data) else b""
            start = held_end
            index += 1
        if not data:
            return True
        return self._put(index, advance(expected, start), data)

    def take_ready(self, expected: int) -> bytes:
        while self._segments:
            sequence, data = self._segments[0]
            behind = distance(expected, sequence)
            if behind >= HALF:
                return b""
            self._segments.pop(0)
            self.held_bytes -= len(data)
            if behind < len(data):
                return data[behind:]
        return b""

    def clear(self) -> None:
        self._segments = []
        self.held_bytes = 0

    def _put(self, index: int, sequence: int, data: bytes) -> bool:
        if len(self._segments) == self._max_segments:
            return False
        self._segments.insert(index, (sequence, data))
        self.held_bytes += len(data)
        return True
