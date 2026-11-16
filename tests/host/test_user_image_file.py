import pytest

from kernel_tool.images.user_image import (
    GUARD_BYTES,
    HEADER,
    MAGIC,
    VERSION,
    read_header,
    with_load_base,
)
from kernel_tool.outcome import CheckError

LOAD_BASE = 0x81000000
FILE_BYTES = HEADER.size + 16
ENTRY = LOAD_BASE + HEADER.size
TEXT_BYTES = 0x2000
RODATA_BYTES = 0x1000
DATA_BYTES = 0x3000
HEAP_BYTES = 0x4000
STACK_BYTES = 0x1000


def image(magic: bytes = MAGIC, version: int = VERSION) -> bytes:
    header = HEADER.pack(
        magic,
        version,
        LOAD_BASE,
        FILE_BYTES,
        ENTRY,
        TEXT_BYTES,
        RODATA_BYTES,
        DATA_BYTES,
        HEAP_BYTES,
        STACK_BYTES,
    )
    return header + bytes(16)


def test_header_fields_are_read_in_file_order() -> None:
    header = read_header(image())

    assert header.load_base == LOAD_BASE
    assert header.file_bytes == FILE_BYTES
    assert header.entry == ENTRY
    assert header.text_bytes == TEXT_BYTES
    assert header.rodata_bytes == RODATA_BYTES
    assert header.data_bytes == DATA_BYTES
    assert header.heap_bytes == HEAP_BYTES
    assert header.stack_bytes == STACK_BYTES


def test_memory_adds_the_segments_the_heap_the_guard_and_the_stack() -> None:
    expected = TEXT_BYTES + RODATA_BYTES + DATA_BYTES + HEAP_BYTES + GUARD_BYTES + STACK_BYTES

    assert read_header(image()).memory_bytes == expected


def test_moving_the_load_base_changes_only_that_field() -> None:
    original = image()

    moved = with_load_base(original, LOAD_BASE + 0x1000)

    assert read_header(moved).load_base == LOAD_BASE + 0x1000
    assert moved[:8] == original[:8]
    assert moved[16:] == original[16:]


@pytest.mark.parametrize(
    "broken",
    [image()[: HEADER.size - 1], image(magic=b"ELF\x7f"), image(version=VERSION + 1), b""],
)
def test_unrecognized_images_are_rejected(broken: bytes) -> None:
    with pytest.raises(CheckError, match="user image"):
        read_header(broken)
