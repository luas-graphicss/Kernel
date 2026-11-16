from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_services.filesystem.format.blocks import encode_block
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    DIRECTORY_MAGIC,
    FIRST_TREE_BLOCK,
    MAX_BLOCKS,
    MIN_BLOCKS,
    ROOT_NODE,
    SUPERBLOCK_SLOTS,
)
from kernel_services.filesystem.format.superblock import Superblock, encode_superblock, slot_of
from kernel_services.filesystem.recovery.mount import FIRST_GENERATION
from kernel_services.filesystem.storage import BlockStore


def volume_blocks(store: BlockStore) -> int:
    return store.blocks if store.blocks < MAX_BLOCKS else MAX_BLOCKS


def create_volume(store: BlockStore, volume: int) -> Superblock:
    total_blocks = volume_blocks(store)
    if total_blocks < MIN_BLOCKS:
        raise KernelError(INVALID_ARGUMENT, "device is smaller than the smallest volume")
    root = encode_block(DIRECTORY_MAGIC, FIRST_GENERATION, b"")
    superblock = Superblock(
        generation=FIRST_GENERATION,
        total_blocks=total_blocks,
        next_node=ROOT_NODE + 1,
        root_block=FIRST_TREE_BLOCK,
        root_checksum=store.checksum(root),
        volume=volume,
    )
    for slot in range(SUPERBLOCK_SLOTS):
        store.write(slot, bytes(BLOCK_BYTES))
    store.write(FIRST_TREE_BLOCK, root)
    store.flush()
    store.write(slot_of(FIRST_GENERATION), encode_superblock(superblock, store))
    store.flush()
    return superblock
