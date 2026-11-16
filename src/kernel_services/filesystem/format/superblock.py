from kernel_protocol.errors.codes import UNSUPPORTED, KernelError
from kernel_services.filesystem.format.codec import corrupted, get, put
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    FIRST_TREE_BLOCK,
    FORMAT_VERSION,
    MAX_BLOCKS,
    MIN_BLOCKS,
    ROOT_NODE,
    SUPERBLOCK_BLOCK_BYTES,
    SUPERBLOCK_BYTES,
    SUPERBLOCK_CHECKSUM,
    SUPERBLOCK_GENERATION,
    SUPERBLOCK_MAGIC,
    SUPERBLOCK_NEXT_NODE,
    SUPERBLOCK_PADDING,
    SUPERBLOCK_RESERVED,
    SUPERBLOCK_ROOT_BLOCK,
    SUPERBLOCK_ROOT_CHECKSUM,
    SUPERBLOCK_SLOTS,
    SUPERBLOCK_TOTAL_BLOCKS,
    SUPERBLOCK_VERSION,
    SUPERBLOCK_VOLUME,
)
from kernel_services.filesystem.storage import BlockStore


class Superblock:
    def __init__(
        self,
        generation: int,
        total_blocks: int,
        next_node: int,
        root_block: int,
        root_checksum: int,
        volume: int,
    ) -> None:
        self.generation = generation
        self.total_blocks = total_blocks
        self.next_node = next_node
        self.root_block = root_block
        self.root_checksum = root_checksum
        self.volume = volume


def slot_of(generation: int) -> int:
    return generation % SUPERBLOCK_SLOTS


def encode_superblock(superblock: Superblock, store: BlockStore) -> bytes:
    fields = (
        SUPERBLOCK_MAGIC
        + put(FORMAT_VERSION, 4)
        + put(BLOCK_BYTES, 4)
        + put(superblock.total_blocks, 4)
        + bytes(4)
        + put(superblock.generation, 8)
        + put(superblock.next_node, 8)
        + put(superblock.root_block, 4)
        + put(superblock.root_checksum, 4)
        + put(superblock.volume, 8)
        + bytes(4)
    )
    return fields + put(store.checksum(fields), 4) + bytes(BLOCK_BYTES - SUPERBLOCK_BYTES)


def check_geometry(block: bytes, slot: int, store: BlockStore) -> None:
    total_blocks = get(block, SUPERBLOCK_TOTAL_BLOCKS, 4)
    generation = get(block, SUPERBLOCK_GENERATION, 8)
    root_block = get(block, SUPERBLOCK_ROOT_BLOCK, 4)
    if get(block, SUPERBLOCK_RESERVED, 4) != 0 or get(block, SUPERBLOCK_PADDING, 4) != 0:
        raise corrupted("superblock uses a reserved field")
    if total_blocks < MIN_BLOCKS or total_blocks > MAX_BLOCKS:
        raise corrupted("superblock declares a size outside the format limits")
    if total_blocks > store.blocks:
        raise corrupted("volume is larger than the device that holds it")
    if generation == 0 or slot_of(generation) != slot:
        raise corrupted("superblock generation does not belong to its slot")
    if root_block < FIRST_TREE_BLOCK or root_block >= total_blocks:
        raise corrupted("superblock points outside the volume")
    if get(block, SUPERBLOCK_NEXT_NODE, 8) <= ROOT_NODE:
        raise corrupted("superblock would reuse the root node number")


def decode_superblock(block: bytes, slot: int, store: BlockStore) -> Superblock:
    if block[: len(SUPERBLOCK_MAGIC)] != SUPERBLOCK_MAGIC:
        raise corrupted("slot does not hold a superblock")
    if (
        get(block, SUPERBLOCK_VERSION, 4) != FORMAT_VERSION
        or get(block, SUPERBLOCK_BLOCK_BYTES, 4) != BLOCK_BYTES
    ):
        raise KernelError(UNSUPPORTED, "superblock belongs to another format version")
    if store.checksum(block[:SUPERBLOCK_CHECKSUM]) != get(block, SUPERBLOCK_CHECKSUM, 4):
        raise corrupted("superblock checksum does not match")
    check_geometry(block, slot, store)
    return Superblock(
        generation=get(block, SUPERBLOCK_GENERATION, 8),
        total_blocks=get(block, SUPERBLOCK_TOTAL_BLOCKS, 4),
        next_node=get(block, SUPERBLOCK_NEXT_NODE, 8),
        root_block=get(block, SUPERBLOCK_ROOT_BLOCK, 4),
        root_checksum=get(block, SUPERBLOCK_ROOT_CHECKSUM, 4),
        volume=get(block, SUPERBLOCK_VOLUME, 8),
    )
