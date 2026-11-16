import zlib

from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_services.filesystem.storage import BlockStore


class ImageStore(BlockStore):
    def __init__(
        self, content: bytes | bytearray, *, writable: bool = True, durable: bool = True
    ) -> None:
        super().__init__(len(content) // BLOCK_BYTES, writable, durable)
        self.content = bytearray(content)

    def read(self, block: int) -> bytes:
        start = self._offset(block)
        return bytes(self.content[start : start + BLOCK_BYTES])

    def write(self, block: int, data: bytes) -> None:
        if len(data) != BLOCK_BYTES:
            raise KernelError(INVALID_ARGUMENT, "a block is written whole")
        start = self._offset(block)
        self.content[start : start + BLOCK_BYTES] = data

    def flush(self) -> None:
        return

    def checksum(self, data: bytes, seed: int = 0) -> int:
        return zlib.crc32(data, seed)

    def _offset(self, block: int) -> int:
        if block < 0 or block >= self.blocks:
            raise KernelError(INVALID_ARGUMENT, "block outside the image")
        return block * BLOCK_BYTES
