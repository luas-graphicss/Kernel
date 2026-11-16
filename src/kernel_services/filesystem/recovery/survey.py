from kernel_services.filesystem.allocation.bitmap import Bitmap
from kernel_services.filesystem.format.blocks import decode_block
from kernel_services.filesystem.format.codec import corrupted
from kernel_services.filesystem.format.directory import Entry, decode_entries
from kernel_services.filesystem.format.index import blocks_for, decode_index
from kernel_services.filesystem.format.layout import (
    DIRECTORY_MAGIC,
    FIRST_TREE_BLOCK,
    INDEX_MAGIC,
    KIND_DIRECTORY,
    MAX_DEPTH,
    NO_BLOCK,
    ROOT_NODE,
    SUPERBLOCK_SLOTS,
)
from kernel_services.filesystem.format.superblock import Superblock
from kernel_services.filesystem.storage import BlockStore, read_verified


class Survey:
    def __init__(self, superblock: Superblock) -> None:
        self.superblock = superblock
        self.reachable = Bitmap(superblock.total_blocks)
        self.used_blocks = SUPERBLOCK_SLOTS
        self.directories = 0
        self.files = 0
        self.data_blocks = 0
        self.file_bytes = 0
        self.nodes: dict[int, bool] = {ROOT_NODE: True}
        for slot in range(SUPERBLOCK_SLOTS):
            self.reachable.set(slot)

    def claim(self, block: int) -> None:
        if block < FIRST_TREE_BLOCK or block >= self.superblock.total_blocks:
            raise corrupted(f"pointer to block {block} leaves the volume")
        if self.reachable.test(block):
            raise corrupted(f"block {block} is referenced twice")
        self.reachable.set(block)
        self.used_blocks += 1

    def number(self, node: int) -> None:
        if node <= ROOT_NODE or node >= self.superblock.next_node or node in self.nodes:
            raise corrupted(f"node number {node} is repeated or was never assigned")
        self.nodes[node] = True


def survey_file(
    store: BlockStore, found: Survey, entry: Entry, newest_generation: int, deep: bool
) -> None:
    count = blocks_for(entry.size)
    found.files += 1
    found.file_bytes += entry.size
    if count == 0:
        if entry.block != NO_BLOCK:
            raise corrupted("empty file points to an index block")
        return
    found.claim(entry.block)
    index = read_verified(store, entry.block, entry.checksum)
    block_map = decode_index(decode_block(index, INDEX_MAGIC, newest_generation)[1], count)
    for position in range(count):
        if block_map.blocks[position] == NO_BLOCK:
            continue
        found.claim(block_map.blocks[position])
        found.data_blocks += 1
        if deep:
            read_verified(store, block_map.blocks[position], block_map.checksums[position])


def survey_tree(store: BlockStore, superblock: Superblock, deep: bool) -> Survey:
    found = Survey(superblock)
    pending = [(superblock.root_block, superblock.root_checksum, superblock.generation, 1)]
    while pending:
        block, checksum, newest_generation, depth = pending.pop()
        found.claim(block)
        directory = read_verified(store, block, checksum)
        generation, payload = decode_block(directory, DIRECTORY_MAGIC, newest_generation)
        entries = decode_entries(payload)
        found.directories += 1
        for name in sorted(entries):
            entry = entries[name]
            found.number(entry.node)
            if entry.kind != KIND_DIRECTORY:
                survey_file(store, found, entry, generation, deep)
            elif depth == MAX_DEPTH:
                raise corrupted("directories nest deeper than the format allows")
            else:
                pending.append((entry.block, entry.checksum, generation, depth + 1))
    return found
