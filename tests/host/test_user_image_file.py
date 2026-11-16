import pytest

from kernel_tool.images.user_image import HEADER, MAGIC, VERSION, read_header, with_load_base
from kernel_tool.outcome import CheckError

LOAD_BASE = 0x81000000


def image(magic: bytes = MAGIC, version: int = VERSION) -> bytes:
    header = HEADER.pack(magic, version, LOAD_BASE, 72, 0x3000, LOAD_BASE + 56, 0x1000, 0x800)
    return header + bytes(16)


def test_header_fields_are_read_in_file_order() -> None:
    header = read_header(image())

    assert header.load_base == LOAD_BASE
    assert header.file_bytes == 72
    assert header.memory_bytes == 0x3000
    assert header.entry == LOAD_BASE + 56
    assert header.heap_bytes == 0x1000
    assert header.stack_bytes == 0x800


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
