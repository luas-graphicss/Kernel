import pytest

from doubles.stores import formatted, fresh_volume
from kernel_protocol.errors.codes import CORRUPTED, UNSUPPORTED, KernelError
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    FORMAT_VERSION,
    HEADER_BYTES,
    KIND_FILE,
    MIN_BLOCKS,
    SUPERBLOCK_GENERATION,
    SUPERBLOCK_VERSION,
)
from kernel_services.filesystem.format.superblock import slot_of
from kernel_services.filesystem.recovery.mount import (
    CLEAN,
    GENERATION_GAP,
    NEWEST_ROOT_DAMAGED,
    PREVIOUS_ROOT_DAMAGED,
    RECOVERED,
    mount,
)
from kernel_services.filesystem.volume import Volume
from kernel_tool.corpus.crafting import (
    erase_block,
    flip_byte,
    newest_superblock,
    patch_superblock,
)
from kernel_tool.storage.image_store import ImageStore

CONTENT = bytes(range(200)) * 30


def committed(commits: int) -> ImageStore:
    store, volume = fresh_volume()
    for commit in range(commits):
        file = volume.create(volume.root(), bytes(f"file-{commit}", "ascii"), KIND_FILE)
        volume.write(file, 0, CONTENT)
        volume.sync()
    return store


def refusal(store: ImageStore) -> KernelError:
    with pytest.raises(KernelError) as raised:
        mount(store, True)
    return raised.value


def test_volume_with_two_consecutive_roots_mounts_clean_and_protects_the_previous_one() -> None:
    store = committed(2)

    mounted = mount(store, True)

    assert (mounted.reason, mounted.read_only) == (CLEAN, False)
    assert mounted.superblock.generation == 3
    assert mounted.retiring != []
    assert all(not mounted.survey.reachable.test(block) for block in mounted.retiring)


def test_lost_newest_superblock_falls_back_to_the_previous_root() -> None:
    store = committed(2)
    erase_block(store, slot_of(3))

    mounted = mount(store, True)

    assert (mounted.reason, mounted.read_only) == (RECOVERED, False)
    assert mounted.superblock.generation == 2
    assert Volume(store).listing(Volume(store).root()) == [(b"file-0", KIND_FILE, len(CONTENT))]


def test_damaged_tree_of_the_newest_root_mounts_the_previous_one_read_only() -> None:
    store = committed(2)
    flip_byte(store, newest_superblock(store).root_block, HEADER_BYTES)

    mounted = mount(store, False)

    assert (mounted.reason, mounted.read_only) == (NEWEST_ROOT_DAMAGED, True)
    assert mounted.superblock.generation == 2


def test_damaged_previous_root_keeps_the_newest_writable_and_reports_it() -> None:
    store = committed(2)
    previous = mount(store, False).retiring[0]
    flip_byte(store, previous, HEADER_BYTES)

    mounted = mount(store, False)

    assert (mounted.reason, mounted.read_only) == (PREVIOUS_ROOT_DAMAGED, False)
    assert mounted.superblock.generation == 3
    assert mounted.retiring == []


def test_generations_that_are_not_consecutive_mount_read_only() -> None:
    store = committed(2)
    patch_superblock(store, slot_of(3), SUPERBLOCK_GENERATION, 8, 5)

    mounted = mount(store, True)

    assert (mounted.reason, mounted.read_only) == (GENERATION_GAP, True)
    assert mounted.superblock.generation == 5


def test_data_damage_is_found_at_mount_only_by_the_deep_survey() -> None:
    store = committed(2)
    volume = Volume(store)
    newest_file = volume.lookup(volume.root(), b"file-1")
    flip_byte(store, newest_file.map.blocks[0], 0)

    assert mount(store, False).reason == CLEAN
    assert mount(store, True).reason == NEWEST_ROOT_DAMAGED
    with pytest.raises(KernelError) as raised:
        Volume(store).read(Volume(store).lookup(Volume(store).root(), b"file-1"), 0, 16)
    assert raised.value.code == CORRUPTED


def test_unknown_format_in_any_slot_refuses_the_mount_without_falling_back() -> None:
    store = committed(2)
    patch_superblock(store, slot_of(3), SUPERBLOCK_VERSION, 4, FORMAT_VERSION + 1)

    assert refusal(store).code == UNSUPPORTED


def test_blank_or_tiny_devices_are_refused_and_never_formatted() -> None:
    blank = ImageStore(bytes(64 * BLOCK_BYTES))
    tiny = ImageStore(formatted(MIN_BLOCKS)[: (MIN_BLOCKS - 1) * BLOCK_BYTES])

    assert refusal(blank).code == CORRUPTED
    assert refusal(tiny).code == CORRUPTED
    assert bytes(blank.content) == bytes(64 * BLOCK_BYTES)
