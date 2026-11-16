from kernel_services.filesystem.format.codec import corrupted, get, put
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    INDEX_LEVEL_DATA,
    INDEX_PREFIX_BYTES,
    NO_BLOCK,
    POINTER_BYTES,
    POINTER_CHECKSUM,
)


class BlockMap:
    def __init__(self) -> None:
        self.blocks: list[int] = []
        self.checksums: list[int] = []

    def resize(self, count: int) -> None:
        while len(self.blocks) > count:
            self.blocks.pop()
            self.checksums.pop()
        while len(self.blocks) < count:
            self.blocks.append(NO_BLOCK)
            self.checksums.append(0)

    def allocated(self) -> list[int]:
        return [block for block in self.blocks if block != NO_BLOCK]


def blocks_for(size: int) -> int:
    return (size + BLOCK_BYTES - 1) // BLOCK_BYTES


def encode_index(block_map: BlockMap) -> bytes:
    pointers = [
        put(block_map.blocks[position], 4) + put(block_map.checksums[position], 4)
        for position in range(len(block_map.blocks))
    ]
    return put(INDEX_LEVEL_DATA, 1) + bytes(INDEX_PREFIX_BYTES - 1) + b"".join(pointers)


def decode_index(payload: bytes, expected_blocks: int) -> BlockMap:
    block_map = BlockMap()
    if len(payload) != INDEX_PREFIX_BYTES + expected_blocks * POINTER_BYTES:
        raise corrupted("file index does not cover the size of its file")
    if payload[:INDEX_PREFIX_BYTES] != bytes(INDEX_PREFIX_BYTES):
        raise corrupted("file index has an unknown level")
    for position in range(expected_blocks):
        offset = INDEX_PREFIX_BYTES + position * POINTER_BYTES
        block = get(payload, offset, 4)
        checksum = get(payload, offset + POINTER_CHECKSUM, 4)
        if block == NO_BLOCK and checksum != 0:
            raise corrupted("file index gives a checksum to a hole")
        block_map.blocks.append(block)
        block_map.checksums.append(checksum)
    return block_map
