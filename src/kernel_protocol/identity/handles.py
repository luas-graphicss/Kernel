from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    INVALID_HANDLE,
    LIMIT_EXCEEDED,
    KernelError,
)

INDEX_BITS = 24
GENERATION_BITS = 32
INDEX_MASK = (1 << INDEX_BITS) - 1
MAX_CAPACITY = 1 << INDEX_BITS
FIRST_GENERATION = 1
INVALID_HANDLE_VALUE = 0


def pack_handle(index: int, generation: int) -> int:
    return (generation << INDEX_BITS) | index


def handle_index(handle: int) -> int:
    return handle & INDEX_MASK


def handle_generation(handle: int) -> int:
    return handle >> INDEX_BITS


class HandleTable:
    def __init__(self, capacity: int, generation_bits: int) -> None:
        if capacity < 1 or capacity > MAX_CAPACITY:
            raise KernelError(INVALID_ARGUMENT, "handle table capacity out of range")
        if generation_bits < 1 or generation_bits > GENERATION_BITS:
            raise KernelError(INVALID_ARGUMENT, "generation width out of range")
        self.capacity = capacity
        self.max_generation = (1 << generation_bits) - 1
        self.live = 0
        self.retired = 0
        self._generations = [FIRST_GENERATION] * capacity
        self._occupied = [False] * capacity
        self._free = list(range(capacity - 1, -1, -1))

    def free_slots(self) -> int:
        return len(self._free)

    def allocate(self) -> int:
        if not self._free:
            raise KernelError(LIMIT_EXCEEDED, "handle table has no free slot")
        index = self._free.pop()
        self._occupied[index] = True
        self.live += 1
        return pack_handle(index, self._generations[index])

    def resolve(self, handle: int) -> int:
        if handle <= INVALID_HANDLE_VALUE or handle >> (INDEX_BITS + GENERATION_BITS) != 0:
            raise KernelError(INVALID_HANDLE, "handle is zero or uses reserved bits")
        index = handle_index(handle)
        if index >= self.capacity:
            raise KernelError(INVALID_HANDLE, "handle index is outside the table")
        if not self._occupied[index] or self._generations[index] != handle_generation(handle):
            raise KernelError(INVALID_HANDLE, "handle generation is stale")
        return index

    def release(self, handle: int) -> None:
        index = self.resolve(handle)
        self._occupied[index] = False
        self.live -= 1
        if self._generations[index] == self.max_generation:
            self.retired += 1
            return
        self._generations[index] += 1
        self._free.append(index)
