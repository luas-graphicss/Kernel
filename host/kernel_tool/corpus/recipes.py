from collections.abc import Callable

from kernel_services.filesystem.creation import create_volume
from kernel_services.filesystem.format.directory import Entry
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    FORMAT_VERSION,
    HEADER_BYTES,
    KIND_DIRECTORY,
    KIND_FILE,
    MIN_BLOCKS,
    SUPERBLOCK_BLOCK_BYTES,
    SUPERBLOCK_GENERATION,
    SUPERBLOCK_SLOTS,
    SUPERBLOCK_VERSION,
)
from kernel_services.filesystem.format.superblock import Superblock, slot_of
from kernel_services.filesystem.transactions.nodes import FileNode
from kernel_services.filesystem.volume import Volume
from kernel_tool.corpus.crafting import (
    erase_block,
    flip_byte,
    newest_superblock,
    patch_superblock,
    read_root,
    write_root,
)
from kernel_tool.outcome import CheckError
from kernel_tool.storage.image_store import ImageStore

CORPUS_BLOCKS = 32
CORPUS_VOLUME = 0x434F52505553
NOTES = b"notes"
README = b"readme.txt"
ENTRY = b"entry.txt"
COPY = b"copy.txt"
README_TEXT = b"kernel corpus\n"
ENTRY_CONTENT = bytes(range(256)) * 20
WORD_BYTES = 4
GENERATION_BYTES = 8

type RootEdit = Callable[[Superblock, dict[bytes, Entry]], None]


def empty_store() -> ImageStore:
    store = ImageStore(bytes(CORPUS_BLOCKS * BLOCK_BYTES))
    create_volume(store, CORPUS_VOLUME)
    return store


def populated_store() -> ImageStore:
    store = empty_store()
    volume = Volume(store)
    notes = volume.create(volume.root(), NOTES, KIND_DIRECTORY)
    readme = volume.create(volume.root(), README, KIND_FILE)
    volume.write(readme, 0, README_TEXT)
    volume.sync()
    entry = volume.create(notes, ENTRY, KIND_FILE)
    volume.write(entry, 0, ENTRY_CONTENT)
    volume.sync()
    return store


def newest_slot(store: ImageStore) -> int:
    return slot_of(newest_superblock(store).generation)


def single_root_store() -> ImageStore:
    store = populated_store()
    erase_block(store, SUPERBLOCK_SLOTS - 1 - newest_slot(store))
    return store


def image_of(store: ImageStore) -> bytes:
    return bytes(store.content)


def with_both_superblocks(offset: int, width: int, value: int) -> bytes:
    store = populated_store()
    for slot in range(SUPERBLOCK_SLOTS):
        patch_superblock(store, slot, offset, width, value)
    return image_of(store)


def with_newest_generation(increment: int) -> bytes:
    store = populated_store()
    generation = newest_superblock(store).generation + increment
    patch_superblock(store, newest_slot(store), SUPERBLOCK_GENERATION, GENERATION_BYTES, generation)
    return image_of(store)


def with_edited_root(edit: RootEdit, generation_shift: int = 0) -> bytes:
    store = single_root_store()
    superblock = newest_superblock(store)
    generation, entries = read_root(store, superblock)
    edit(superblock, entries)
    write_root(store, superblock, generation + generation_shift, entries)
    return image_of(store)


def truncated(blocks: int, extra_bytes: int = 0) -> bytes:
    return image_of(populated_store())[: blocks * BLOCK_BYTES + extra_bytes]


def empty_volume() -> bytes:
    return image_of(empty_store())


def populated_volume() -> bytes:
    return image_of(populated_store())


def single_superblock() -> bytes:
    return image_of(single_root_store())


def superblock_checksum_mismatch() -> bytes:
    store = populated_store()
    flip_byte(store, newest_slot(store), SUPERBLOCK_GENERATION)
    return image_of(store)


def both_superblocks_damaged() -> bytes:
    store = populated_store()
    for slot in range(SUPERBLOCK_SLOTS):
        flip_byte(store, slot, SUPERBLOCK_GENERATION)
    return image_of(store)


def newer_format_in_newest_slot() -> bytes:
    store = populated_store()
    patch_superblock(store, newest_slot(store), SUPERBLOCK_VERSION, WORD_BYTES, FORMAT_VERSION + 1)
    return image_of(store)


def newest_root_damaged() -> bytes:
    store = populated_store()
    flip_byte(store, newest_superblock(store).root_block, HEADER_BYTES)
    return image_of(store)


def damaged_file_data() -> bytes:
    store = populated_store()
    volume = Volume(store)
    entry = volume.lookup(volume.lookup(volume.root(), NOTES), ENTRY)
    if not isinstance(entry, FileNode):
        raise CheckError("the corpus volume lost the file its recipe damages")
    flip_byte(store, entry.map.blocks[0], 0)
    return image_of(store)


def reference_twice(superblock: Superblock, entries: dict[bytes, Entry]) -> None:
    readme = entries[README]
    entries[COPY] = Entry(
        KIND_FILE, superblock.next_node, readme.block, readme.checksum, readme.size
    )
    superblock.next_node += 1


def close_cycle(superblock: Superblock, entries: dict[bytes, Entry]) -> None:
    entries[NOTES].block = superblock.root_block


def point_outside(superblock: Superblock, entries: dict[bytes, Entry]) -> None:
    entries[README].block = superblock.total_blocks + 5


def point_at_directory(_superblock: Superblock, entries: dict[bytes, Entry]) -> None:
    entries[README].block = entries[NOTES].block
    entries[README].checksum = entries[NOTES].checksum


def repeat_node(_superblock: Superblock, entries: dict[bytes, Entry]) -> None:
    entries[README].node = entries[NOTES].node


def keep_entries(_superblock: Superblock, _entries: dict[bytes, Entry]) -> None:
    return


RECIPES: dict[str, Callable[[], bytes]] = {
    "empty-volume": empty_volume,
    "populated-volume": populated_volume,
    "single-superblock": single_superblock,
    "superblock-checksum-mismatch": superblock_checksum_mismatch,
    "generation-in-wrong-slot": lambda: with_newest_generation(1),
    "generation-gap": lambda: with_newest_generation(2),
    "newest-root-damaged": newest_root_damaged,
    "damaged-file-data": damaged_file_data,
    "truncated-to-superblocks": lambda: truncated(SUPERBLOCK_SLOTS),
    "truncated-tree": lambda: truncated(MIN_BLOCKS),
    "truncated-inside-a-block": lambda: truncated(MIN_BLOCKS, BLOCK_BYTES // 2),
    "unknown-format-version": lambda: with_both_superblocks(
        SUPERBLOCK_VERSION, WORD_BYTES, FORMAT_VERSION + 1
    ),
    "unknown-block-size": lambda: with_both_superblocks(
        SUPERBLOCK_BLOCK_BYTES, WORD_BYTES, 2 * BLOCK_BYTES
    ),
    "newer-format-in-newest-slot": newer_format_in_newest_slot,
    "both-superblocks-damaged": both_superblocks_damaged,
    "block-referenced-twice": lambda: with_edited_root(reference_twice),
    "directory-cycle": lambda: with_edited_root(close_cycle),
    "pointer-outside-volume": lambda: with_edited_root(point_outside),
    "index-with-wrong-type": lambda: with_edited_root(point_at_directory),
    "node-number-repeated": lambda: with_edited_root(repeat_node),
    "block-newer-than-its-root": lambda: with_edited_root(keep_entries, generation_shift=1),
}


def build(name: str) -> bytes:
    recipe = RECIPES.get(name)
    if recipe is None:
        raise CheckError(f"the corpus has no recipe named {name!r}")
    return recipe()
