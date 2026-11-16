import pytest

from doubles.stores import FailingStore, formatted, fresh_volume, remounted
from kernel_protocol.errors.codes import (
    ALREADY_EXISTS,
    INVALID_ARGUMENT,
    IO_ERROR,
    IS_A_DIRECTORY,
    LIMIT_EXCEEDED,
    NO_SPACE,
    NOT_A_DIRECTORY,
    NOT_EMPTY,
    NOT_FOUND,
    READ_ONLY,
    UNKNOWN_OUTCOME,
    KernelError,
)
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    KIND_DIRECTORY,
    KIND_FILE,
    MAX_DEPTH,
    MAX_FILE_BYTES,
)
from kernel_services.filesystem.recovery.digest import tree_digest
from kernel_services.filesystem.recovery.mount import DEVICE_READ_ONLY, DEVICE_WITHOUT_FLUSH
from kernel_services.filesystem.volume import Volume
from kernel_tool.storage.image_store import ImageStore

PATTERN = bytes(range(256)) * 40
BLOCKS = 64
STAGING_WRITE = 1
STAGING_FLUSH = 1
PUBLISHING_FLUSH = 2


def code_of(call, *arguments) -> int:
    with pytest.raises(KernelError) as raised:
        call(*arguments)
    return raised.value.code


def file_in(volume: Volume, name: bytes = b"file.bin", content: bytes = b""):
    created = volume.create(volume.root(), name, KIND_FILE)
    if content:
        volume.write(created, 0, content)
    return created


def fill(volume: Volume, file) -> int:
    offset = 0
    while True:
        try:
            offset += volume.write(file, offset, PATTERN)
        except KernelError as error:
            assert error.code == NO_SPACE
            return offset


def test_file_reads_back_what_was_written_and_stops_at_its_end() -> None:
    _store, volume = fresh_volume()
    file = file_in(volume)

    assert volume.write(file, 0, b"") == 0
    assert volume.write(file, 0, PATTERN) == len(PATTERN)
    assert volume.read(file, 0, len(PATTERN)) == PATTERN
    assert volume.read(file, len(PATTERN) - 10, 100) == PATTERN[-10:]
    assert volume.read(file, len(PATTERN), 8) == b""
    assert volume.read(file, 0, 0) == b""
    assert volume.listing(volume.root()) == [(b"file.bin", KIND_FILE, len(PATTERN))]


def test_write_past_the_end_leaves_a_hole_of_zeros_without_blocks() -> None:
    _store, volume = fresh_volume()
    file = file_in(volume)
    free = volume.free_blocks()

    volume.write(file, 10 * BLOCK_BYTES, b"tail")

    assert volume.read(file, 0, 10 * BLOCK_BYTES) == bytes(10 * BLOCK_BYTES)
    assert volume.read(file, 10 * BLOCK_BYTES, 4) == b"tail"
    assert free - volume.free_blocks() == 1


def test_truncation_never_exposes_what_it_dropped() -> None:
    _store, volume = fresh_volume()
    file = file_in(volume, content=PATTERN)

    volume.truncate(file, 5)
    volume.truncate(file, 9000)

    assert volume.read(file, 0, 9000) == PATTERN[:5] + bytes(8995)


def test_offsets_sizes_and_the_largest_file_are_bounded() -> None:
    _store, volume = fresh_volume()
    file = file_in(volume)

    assert code_of(volume.write, file, -1, b"x") == INVALID_ARGUMENT
    assert code_of(volume.read, file, -1, 1) == INVALID_ARGUMENT
    assert code_of(volume.truncate, file, -1) == INVALID_ARGUMENT
    assert code_of(volume.write, file, MAX_FILE_BYTES, b"x") == LIMIT_EXCEEDED
    assert code_of(volume.truncate, file, MAX_FILE_BYTES + 1) == LIMIT_EXCEEDED


def test_names_are_unique_and_nodes_keep_their_kind() -> None:
    _store, volume = fresh_volume()
    root = volume.root()
    file = file_in(volume)
    directory = volume.create(root, b"dir", KIND_DIRECTORY)

    assert code_of(volume.create, root, b"file.bin", KIND_DIRECTORY) == ALREADY_EXISTS
    assert code_of(volume.create, root, b"a/b", KIND_FILE) == INVALID_ARGUMENT
    assert code_of(volume.lookup, root, b"missing") == NOT_FOUND
    assert code_of(volume.lookup, file, b"below") == NOT_A_DIRECTORY
    assert code_of(volume.read, directory, 0, 1) == IS_A_DIRECTORY
    assert code_of(volume.write, directory, 0, b"x") == IS_A_DIRECTORY


def test_rename_moves_replaces_and_refuses_what_would_break_the_tree() -> None:
    _store, volume = fresh_volume()
    root = volume.root()
    file_in(volume, b"one", b"1")
    file_in(volume, b"two", b"22")
    directory = volume.create(root, b"dir", KIND_DIRECTORY)
    inner = volume.create(directory, b"inner", KIND_DIRECTORY)

    volume.rename(root, b"one", directory, b"moved")
    volume.rename(root, b"two", directory, b"moved")
    volume.rename(directory, b"moved", directory, b"moved")

    assert volume.read(volume.lookup(directory, b"moved"), 0, 8) == b"22"
    assert [name for name, _kind, _size in volume.listing(root)] == [b"dir"]
    assert code_of(volume.rename, root, b"dir", inner, b"again") == INVALID_ARGUMENT
    assert code_of(volume.rename, directory, b"moved", directory, b"inner") == IS_A_DIRECTORY
    assert code_of(volume.rename, directory, b"inner", directory, b"moved") == NOT_A_DIRECTORY
    assert code_of(volume.rename, root, b"missing", root, b"other") == NOT_FOUND
    assert code_of(volume.remove, root, b"dir") == NOT_EMPTY


def test_removed_file_stays_readable_until_its_last_holder_releases_it() -> None:
    _store, volume = fresh_volume()
    file = file_in(volume, content=PATTERN)
    volume.retain(file)
    free = volume.free_blocks()

    volume.remove(volume.root(), b"file.bin")

    assert volume.read(file, 0, len(PATTERN)) == PATTERN
    assert code_of(volume.write, file, 0, b"late") == NOT_FOUND
    assert volume.free_blocks() == free
    volume.release(file)
    assert volume.free_blocks() > free


def test_directories_nest_only_as_deep_as_the_format_allows() -> None:
    _store, volume = fresh_volume()
    directory = volume.root()
    for _level in range(MAX_DEPTH - 1):
        directory = volume.create(directory, b"d", KIND_DIRECTORY)

    assert code_of(volume.create, directory, b"d", KIND_DIRECTORY) == LIMIT_EXCEEDED
    assert volume.create(directory, b"f", KIND_FILE).kind == KIND_FILE


def test_directory_refuses_an_entry_that_does_not_fit_in_its_block() -> None:
    _store, volume = fresh_volume()
    root = volume.root()
    for index in range(17):
        volume.create(root, bytes(f"{index:02d}", "ascii") + b"n" * 207, KIND_FILE)

    assert code_of(volume.create, root, b"n" * 209, KIND_FILE) == LIMIT_EXCEEDED
    volume.remove(root, b"00" + b"n" * 207)
    assert volume.create(root, b"n" * 209, KIND_FILE).kind == KIND_FILE


def test_only_synced_changes_survive_a_remount() -> None:
    store, volume = fresh_volume()
    file_in(volume, b"kept", PATTERN)
    volume.sync()
    file_in(volume, b"lost", PATTERN)
    volume.write(volume.lookup(volume.root(), b"kept"), 0, b"unsynced")

    again = remounted(store)

    assert again.generation() == volume.generation() == 2
    assert again.listing(again.root()) == [(b"kept", KIND_FILE, len(PATTERN))]
    assert again.read(again.lookup(again.root(), b"kept"), 0, len(PATTERN)) == PATTERN


def test_sync_without_changes_commits_nothing() -> None:
    store, volume = fresh_volume()
    before = bytes(store.content)

    volume.sync()

    assert volume.generation() == 1
    assert bytes(store.content) == before
    assert not volume.has_pending_changes()


def test_full_volume_accepts_part_of_a_write_then_refuses_and_still_commits() -> None:
    store, volume = fresh_volume()
    file = file_in(volume)

    accepted = fill(volume, file)
    volume.sync()

    assert 0 < accepted < BLOCKS * BLOCK_BYTES
    assert accepted % len(PATTERN) != 0
    assert code_of(volume.write, file, accepted + BLOCK_BYTES, b"x") == NO_SPACE
    assert (
        volume.read(file, accepted - 16, 16)
        == (PATTERN * 2)[(accepted - 16) % len(PATTERN) : (accepted - 16) % len(PATTERN) + 16]
    )
    assert remounted(store).listing(remounted(store).root()) == [(b"file.bin", KIND_FILE, accepted)]


def test_space_of_a_removed_file_returns_after_the_roots_that_held_it_are_replaced() -> None:
    _store, volume = fresh_volume()
    file = file_in(volume)
    accepted = fill(volume, file)
    volume.sync()

    volume.remove(volume.root(), b"file.bin")
    again = file_in(volume, b"again.bin")

    assert volume.write(again, 0, bytes(accepted // 2)) == accepted // 2
    assert volume.free_blocks() >= 0


def test_volume_on_a_device_that_refuses_writes_or_has_no_flush_is_read_only() -> None:
    image = formatted(BLOCKS)
    read_only = Volume(ImageStore(image, writable=False))
    volatile = Volume(ImageStore(image, durable=False))

    assert read_only.mounted.reason == DEVICE_READ_ONLY
    assert volatile.mounted.reason == DEVICE_WITHOUT_FLUSH
    for volume in (read_only, volatile):
        assert volume.is_read_only()
        assert code_of(volume.create, volume.root(), b"f", KIND_FILE) == READ_ONLY
        assert code_of(volume.sync) == READ_ONLY
        assert volume.listing(volume.root()) == []


def test_write_error_inside_a_file_keeps_what_was_stored_and_commits_a_valid_tree() -> None:
    store = FailingStore(formatted(BLOCKS))
    volume = Volume(store)
    file = file_in(volume, content=PATTERN)
    volume.sync()
    store.failing_write = store.writes + 2

    assert code_of(volume.write, file, 0, bytes(5 * BLOCK_BYTES)) == IO_ERROR
    volume.sync()
    mounted = remounted(store)

    assert not volume.has_failed()
    assert volume.read(file, 0, MAX_FILE_BYTES) == bytes(BLOCK_BYTES) + PATTERN[BLOCK_BYTES:]
    assert (mounted.generation(), mounted.is_read_only()) == (volume.generation(), False)
    assert mounted.listing(mounted.root()) == [(b"file.bin", KIND_FILE, len(PATTERN))]


def test_write_error_past_the_end_extends_the_file_only_over_what_was_stored() -> None:
    store = FailingStore(formatted(BLOCKS))
    volume = Volume(store)
    file = file_in(volume, content=b"head")
    volume.sync()
    store.failing_write = store.writes + 2

    assert code_of(volume.write, file, 0, PATTERN) == IO_ERROR
    volume.sync()
    mounted = remounted(store)

    assert volume.read(file, 0, MAX_FILE_BYTES) == PATTERN[:BLOCK_BYTES]
    assert (mounted.generation(), mounted.is_read_only()) == (volume.generation(), False)
    assert mounted.listing(mounted.root()) == [(b"file.bin", KIND_FILE, BLOCK_BYTES)]


def test_write_error_while_shortening_a_file_leaves_it_whole() -> None:
    store = FailingStore(formatted(BLOCKS))
    volume = Volume(store)
    file = file_in(volume, content=PATTERN)
    volume.sync()
    store.failing_write = store.writes + 1

    assert code_of(volume.truncate, file, BLOCK_BYTES + 10) == IO_ERROR
    volume.sync()
    mounted = remounted(store)

    assert volume.read(file, 0, MAX_FILE_BYTES) == PATTERN
    assert (mounted.generation(), mounted.is_read_only()) == (volume.generation(), False)
    assert mounted.listing(mounted.root()) == [(b"file.bin", KIND_FILE, len(PATTERN))]


def test_write_error_while_staging_fails_the_commit_and_keeps_the_old_root() -> None:
    store = FailingStore(formatted(BLOCKS))
    volume = Volume(store)
    file_in(volume)
    store.failing_write = store.writes + STAGING_WRITE

    assert code_of(volume.sync) == IO_ERROR
    assert volume.has_failed()
    assert code_of(volume.listing, volume.root()) == IO_ERROR
    assert code_of(volume.create, volume.root(), b"other", KIND_FILE) == IO_ERROR
    assert remounted(store).generation() == 1
    assert remounted(store).listing(remounted(store).root()) == []


def test_flush_error_before_the_superblock_fails_the_commit_for_certain() -> None:
    store = FailingStore(formatted(BLOCKS))
    volume = Volume(store)
    file_in(volume)
    store.failing_flush = store.flushes + STAGING_FLUSH

    assert code_of(volume.sync) == IO_ERROR
    assert remounted(store).generation() == 1


def test_flush_error_after_the_superblock_leaves_the_outcome_unknown() -> None:
    store = FailingStore(formatted(BLOCKS))
    volume = Volume(store)
    file_in(volume, content=PATTERN)
    committed = tree_digest(volume)
    store.failing_flush = store.flushes + PUBLISHING_FLUSH

    assert code_of(volume.sync) == UNKNOWN_OUTCOME
    assert volume.has_failed()
    again = remounted(store)
    assert again.generation() == 2
    assert tree_digest(again) == committed
