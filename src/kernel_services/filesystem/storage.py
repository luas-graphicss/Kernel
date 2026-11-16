from kernel_protocol.errors.codes import UNSUPPORTED, KernelError
from kernel_services.filesystem.format.codec import corrupted

ABSTRACT = "the block store does not implement the operation"


class BlockStore:
    def __init__(self, blocks: int, writable: bool, durable: bool) -> None:
        self.blocks = blocks
        self.writable = writable
        self.durable = durable

    def read(self, block: int) -> bytes:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def write(self, block: int, data: bytes) -> None:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def flush(self) -> None:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def checksum(self, data: bytes, seed: int = 0) -> int:
        raise KernelError(UNSUPPORTED, ABSTRACT)

    def close(self) -> None:
        return


def read_verified(store: BlockStore, block: int, checksum: int) -> bytes:
    data = store.read(block)
    if store.checksum(data) != checksum:
        raise corrupted(f"block {block} does not match the checksum of its pointer")
    return data
