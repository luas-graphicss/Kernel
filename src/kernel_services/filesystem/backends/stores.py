import _process
from kernel_client.blocks import BlockDevice
from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.services.block import FLAG_FLUSH, FLAG_READ_ONLY, SECTOR_BYTES
from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_services.filesystem.storage import BlockStore

SECTORS_PER_BLOCK = BLOCK_BYTES // SECTOR_BYTES
OUTSIDE = "block outside the store"


class GuestStore(BlockStore):
    def checksum(self, data: bytes, seed: int = 0) -> int:
        return _process.crc32(data, seed)

    def check(self, block: int) -> None:
        if block < 0 or block >= self.blocks:
            raise KernelError(INVALID_ARGUMENT, OUTSIDE)


class MemoryStore(GuestStore):
    def __init__(self, blocks: int) -> None:
        super().__init__(blocks, True, True)
        self._content: dict[int, bytes] = {}
        self._empty = bytes(BLOCK_BYTES)

    def read(self, block: int) -> bytes:
        self.check(block)
        return self._content.get(block, self._empty)

    def write(self, block: int, data: bytes) -> None:
        self.check(block)
        self._content[block] = data

    def flush(self) -> None:
        return


class DeviceStore(GuestStore):
    def __init__(self, device: BlockDevice) -> None:
        flags = device.geometry.flags
        super().__init__(
            device.geometry.sectors // SECTORS_PER_BLOCK,
            flags & FLAG_READ_ONLY == 0,
            flags & FLAG_FLUSH != 0,
        )
        self._device = device

    def read(self, block: int) -> bytes:
        self.check(block)
        self._device.read(block * SECTORS_PER_BLOCK, SECTORS_PER_BLOCK)
        return self._device.mapping.read(0, BLOCK_BYTES)

    def write(self, block: int, data: bytes) -> None:
        self.check(block)
        self._device.mapping.write(0, data)
        self._device.write(block * SECTORS_PER_BLOCK, SECTORS_PER_BLOCK)

    def flush(self) -> None:
        self._device.flush()

    def close(self) -> None:
        self._device.close()
