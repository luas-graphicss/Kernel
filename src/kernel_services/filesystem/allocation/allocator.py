from kernel_protocol.errors.codes import NO_SPACE, KernelError
from kernel_services.filesystem.allocation.bitmap import Bitmap
from kernel_services.filesystem.format.layout import FIRST_TREE_BLOCK

VOLUME_FULL = "the volume has no free block"


class Allocator:
    def __init__(self, in_use: Bitmap, free: int, retiring: list[int]) -> None:
        self._in_use = in_use
        self._fresh = Bitmap(in_use.bits)
        self._released: list[int] = []
        self._retiring = retiring
        self._cursor = FIRST_TREE_BLOCK
        self.free = free

    def allocate(self) -> int:
        if self.free == 0:
            raise KernelError(NO_SPACE, VOLUME_FULL)
        while self._in_use.test(self._cursor):
            self._cursor = self._next(self._cursor)
        block = self._cursor
        self._in_use.set(block)
        self._fresh.set(block)
        self._cursor = self._next(block)
        self.free -= 1
        return block

    def is_fresh(self, block: int) -> bool:
        return self._fresh.test(block)

    def release(self, block: int) -> None:
        if self._fresh.test(block):
            self._fresh.clear(block)
            self._in_use.clear(block)
            self.free += 1
        else:
            self._released.append(block)

    def publish(self) -> None:
        for block in self._retiring:
            self._in_use.clear(block)
        self.free += len(self._retiring)
        self._retiring = self._released
        self._released = []
        self._fresh = Bitmap(self._in_use.bits)

    def reclaimable(self) -> int:
        return len(self._retiring) + len(self._released)

    def _next(self, block: int) -> int:
        return block + 1 if block + 1 < self._in_use.bits else FIRST_TREE_BLOCK
