from kernel_protocol.errors.codes import KernelError
from kernel_services.filesystem.format.blocks import decode_block, encode_block
from kernel_services.filesystem.format.codec import put
from kernel_services.filesystem.format.directory import Entry, decode_entries, encode_entries
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    DIRECTORY_MAGIC,
    SUPERBLOCK_CHECKSUM,
    SUPERBLOCK_SLOTS,
)
from kernel_services.filesystem.format.superblock import (
    Superblock,
    decode_superblock,
    encode_superblock,
    slot_of,
)
from kernel_tool.outcome import CheckError
from kernel_tool.storage.image_store import ImageStore

CHECKSUM_BYTES = 4
EVERY_BIT = 0xFF


def newest_superblock(store: ImageStore) -> Superblock:
    found = []
    for slot in range(SUPERBLOCK_SLOTS):
        try:
            found.append(decode_superblock(store.read(slot), slot, store))
        except KernelError:
            continue
    if not found:
        raise CheckError("the image has no valid superblock to edit")
    return max(found, key=lambda superblock: superblock.generation)


def erase_block(store: ImageStore, block: int) -> None:
    store.write(block, bytes(BLOCK_BYTES))


def flip_byte(store: ImageStore, block: int, offset: int) -> None:
    content = bytearray(store.read(block))
    content[offset] ^= EVERY_BIT
    store.write(block, bytes(content))


def patch_superblock(store: ImageStore, slot: int, offset: int, width: int, value: int) -> None:
    content = bytearray(store.read(slot))
    content[offset : offset + width] = put(value, width)
    checksum = store.checksum(bytes(content[:SUPERBLOCK_CHECKSUM]))
    content[SUPERBLOCK_CHECKSUM : SUPERBLOCK_CHECKSUM + CHECKSUM_BYTES] = put(
        checksum, CHECKSUM_BYTES
    )
    store.write(slot, bytes(content))


def read_root(store: ImageStore, superblock: Superblock) -> tuple[int, dict[bytes, Entry]]:
    generation, payload = decode_block(
        store.read(superblock.root_block), DIRECTORY_MAGIC, superblock.generation
    )
    return generation, decode_entries(payload)


def write_root(
    store: ImageStore, superblock: Superblock, generation: int, entries: dict[bytes, Entry]
) -> None:
    block = encode_block(DIRECTORY_MAGIC, generation, encode_entries(entries))
    store.write(superblock.root_block, block)
    superblock.root_checksum = store.checksum(block)
    store.write(slot_of(superblock.generation), encode_superblock(superblock, store))
