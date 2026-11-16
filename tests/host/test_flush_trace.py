import pytest

from kernel_services.filesystem.format.layout import BLOCK_BYTES, KIND_FILE, SUPERBLOCK_SLOTS
from kernel_tool.faults.device_log import (
    DeviceEvent,
    DeviceFlush,
    DeviceWrite,
    describe,
    published_generation,
)
from kernel_tool.faults.recovery import RecordedVolume
from kernel_tool.faults.trace import check_trace
from kernel_tool.faults.write_log import ENTRY, FLAG_FLUSH, HEADER, MAGIC, VERSION, read_write_log
from kernel_tool.outcome import CheckError
from kernel_tool.storage.volumes import create_image

SECTOR_BYTES = 512
SECTORS_PER_BLOCK = BLOCK_BYTES // SECTOR_BYTES
UNSUPPORTED_SECTOR_BYTES = 3000
UNKNOWN_FLAG = 0x8
VOLUME_BLOCKS = 64
VOLUME = 0x5452414345
FIRST_BLOCK = bytes([1]) * BLOCK_BYTES
SECOND_BLOCK = bytes([2]) * BLOCK_BYTES
NO_DIGEST = "00000000"

type Journal = tuple[bytes, list[DeviceEvent], list[tuple[int, str]]]


def padded(record: bytes, sector_bytes: int = SECTOR_BYTES) -> bytes:
    return record + bytes(sector_bytes - len(record))


def log_header(
    entries: int,
    *,
    magic: int = MAGIC,
    version: int = VERSION,
    sector_bytes: int = SECTOR_BYTES,
) -> bytes:
    return padded(HEADER.pack(magic, version, entries, sector_bytes), sector_bytes)


def log_entry(sector: int, data: bytes, flags: int = 0) -> bytes:
    return padded(ENTRY.pack(sector, len(data) // SECTOR_BYTES, flags, 0)) + data


def block_entry(block: int, data: bytes, flags: int = 0) -> bytes:
    return log_entry(block * SECTORS_PER_BLOCK, data, flags)


def write_log(*entries: bytes) -> bytes:
    return log_header(len(entries)) + b"".join(entries)


def journal() -> Journal:
    recorded = RecordedVolume(create_image(VOLUME_BLOCKS, VOLUME))
    volume = recorded.volume
    ledger = volume.create(volume.root(), b"ledger.bin", KIND_FILE)
    volume.write(ledger, 0, b"first")
    volume.sync()
    volume.write(ledger, 5, b" second")
    volume.sync()
    reported = [
        (commit.generation, f"{commit.digest:08x}") for commit in recorded.history.commits[1:]
    ]
    return recorded.base, recorded.store.events, reported


def first_superblock(events: list[DeviceEvent]) -> int:
    return next(
        index for index, event in enumerate(events) if published_generation(event) is not None
    )


def has_failure(failures: tuple[str, ...], text: str) -> bool:
    return any(text in failure for failure in failures)


def test_a_log_is_read_as_block_writes_and_flushes() -> None:
    content = write_log(
        block_entry(5, FIRST_BLOCK + SECOND_BLOCK),
        block_entry(0, b"", FLAG_FLUSH),
        block_entry(9, FIRST_BLOCK, FLAG_FLUSH),
    )

    assert read_write_log(content) == [
        DeviceWrite(5, FIRST_BLOCK),
        DeviceWrite(6, SECOND_BLOCK),
        DeviceFlush(),
        DeviceWrite(9, FIRST_BLOCK),
        DeviceFlush(),
    ]
    assert read_write_log(write_log()) == []


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        (b"", "shorter than its header"),
        (log_header(0, magic=MAGIC + 1), "has magic"),
        (log_header(0, version=VERSION + 1), f"version {VERSION + 1}"),
        (HEADER.pack(MAGIC, VERSION, 0, 0), "sectors of 0 bytes"),
        (
            log_header(0, sector_bytes=UNSUPPORTED_SECTOR_BYTES),
            f"sectors of {UNSUPPORTED_SECTOR_BYTES} bytes",
        ),
        (log_header(1), "ends inside an entry"),
        (log_header(1) + block_entry(1, FIRST_BLOCK)[:-1], "ends inside the data"),
        (write_log(block_entry(1, FIRST_BLOCK, UNKNOWN_FLAG)), "unknown flags 0x8"),
        (write_log(log_entry(1, FIRST_BLOCK)), "not made of whole blocks"),
        (write_log(log_entry(0, bytes(SECTOR_BYTES))), "not made of whole blocks"),
    ],
)
def test_a_malformed_log_is_refused(content: bytes, problem: str) -> None:
    with pytest.raises(CheckError, match=problem):
        read_write_log(content)


def test_only_a_superblock_written_to_its_slot_publishes_a_generation() -> None:
    _base, events, reported = journal()
    superblock = events[first_superblock(events)]
    generation = reported[0][0]

    assert isinstance(superblock, DeviceWrite)
    assert published_generation(superblock) == generation
    assert published_generation(DeviceWrite(SUPERBLOCK_SLOTS, superblock.data)) is None
    assert published_generation(DeviceWrite(0, FIRST_BLOCK)) is None
    assert published_generation(DeviceFlush()) is None
    assert describe(superblock) == f"superblock of generation {generation}"
    assert describe(DeviceWrite(7, FIRST_BLOCK)) == "write of block 7"
    assert describe(DeviceFlush()) == "flush"


def test_a_trace_with_barriers_around_each_superblock_replays_without_failures() -> None:
    base, events, reported = journal()

    result = check_trace(base, events, reported)

    assert result.failures == ()
    assert result.generations == tuple(generation for generation, _digest in reported)
    assert len(result.events) == len(events)
    assert result.images > len(events)


def test_a_superblock_sent_before_its_tree_was_flushed_is_reported() -> None:
    base, events, reported = journal()
    del events[first_superblock(events) - 1]

    result = check_trace(base, events, reported)

    assert has_failure(result.failures, "left before its tree was flushed")


def test_a_superblock_that_is_not_flushed_at_once_is_reported() -> None:
    base, events, reported = journal()
    del events[first_superblock(events) + 1]

    result = check_trace(base, events, reported)

    assert has_failure(result.failures, "was not flushed at once")


def test_reports_and_superblocks_must_name_the_same_generations() -> None:
    base, events, reported = journal()
    never_sent = (reported[-1][0] + 1, NO_DIGEST)

    unreported = check_trace(base, events, reported[:1])
    unsent = check_trace(base, events, [*reported, never_sent])

    assert has_failure(unreported.failures, "reached the device without a report")
    assert has_failure(unsent.failures, "its superblock never reached the device")


def test_a_report_with_another_digest_is_reported() -> None:
    base, events, reported = journal()
    wrong = [(generation, NO_DIGEST) for generation, _digest in reported]

    result = check_trace(base, events, wrong)

    assert has_failure(result.failures, f"instead of {NO_DIGEST}")
