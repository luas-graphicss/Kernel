import pytest

from doubles.stores import formatted
from kernel_protocol.errors.codes import (
    CORRUPTED,
    INVALID_ARGUMENT,
    LIMIT_EXCEEDED,
    UNSUPPORTED,
    KernelError,
)
from kernel_services.filesystem.format import layout
from kernel_services.filesystem.format.blocks import decode_block, encode_block
from kernel_services.filesystem.format.directory import (
    Entry,
    decode_entries,
    encode_entries,
    encode_entry,
)
from kernel_services.filesystem.format.index import BlockMap, decode_index, encode_index
from kernel_services.filesystem.format.names import check_name, is_utf8, name_is_valid
from kernel_services.filesystem.format.superblock import (
    Superblock,
    decode_superblock,
    encode_superblock,
    slot_of,
)
from kernel_tool.corpus.crafting import flip_byte, patch_superblock
from kernel_tool.storage.image_store import ImageStore

BLOCKS = 64
FIRST_SLOT = 1
GENERATION = 7
SUPERBLOCK_PATCHES = [
    ("format version", layout.SUPERBLOCK_VERSION, 4, 2, UNSUPPORTED),
    ("block size", layout.SUPERBLOCK_BLOCK_BYTES, 4, 8192, UNSUPPORTED),
    ("reserved field", layout.SUPERBLOCK_RESERVED, 4, 1, CORRUPTED),
    ("padding", layout.SUPERBLOCK_PADDING, 4, 1, CORRUPTED),
    ("fewer blocks than a volume", layout.SUPERBLOCK_TOTAL_BLOCKS, 4, 7, CORRUPTED),
    ("more blocks than the format", layout.SUPERBLOCK_TOTAL_BLOCKS, 4, 65537, CORRUPTED),
    ("more blocks than the device", layout.SUPERBLOCK_TOTAL_BLOCKS, 4, BLOCKS + 1, CORRUPTED),
    ("generation zero", layout.SUPERBLOCK_GENERATION, 8, 0, CORRUPTED),
    ("generation of the other slot", layout.SUPERBLOCK_GENERATION, 8, 2, CORRUPTED),
    ("root inside the superblocks", layout.SUPERBLOCK_ROOT_BLOCK, 4, 1, CORRUPTED),
    ("root outside the volume", layout.SUPERBLOCK_ROOT_BLOCK, 4, BLOCKS, CORRUPTED),
    ("next node is the root", layout.SUPERBLOCK_NEXT_NODE, 8, 1, CORRUPTED),
]
UTF8_SAMPLES = [
    (b"plain", True),
    (b"a\xc3\xa7\xc3\xa3o", True),
    (b"\xe2\x82\xac", True),
    (b"\xf0\x9d\x84\x9e", True),
    (b"\xf4\x8f\xbf\xbf", True),
    (b"\x80", False),
    (b"\xc0\xaf", False),
    (b"\xc1\xbf", False),
    (b"\xe0\x80\xaf", False),
    (b"\xed\xa0\x80", False),
    (b"\xf0\x80\x80\x80", False),
    (b"\xf4\x90\x80\x80", False),
    (b"\xf5\x80\x80\x80", False),
    (b"\xe2\x82", False),
    (b"\xff", False),
]


def code_of(call, *arguments) -> int:
    with pytest.raises(KernelError) as raised:
        call(*arguments)
    return raised.value.code


def fresh_store() -> ImageStore:
    return ImageStore(formatted(BLOCKS))


def entry(kind: int = layout.KIND_FILE, size: int = 0) -> Entry:
    return Entry(kind, 2, 5, 0x1234, size)


def test_superblock_round_trips_and_lives_in_the_slot_of_its_generation() -> None:
    store = fresh_store()
    written = Superblock(GENERATION, BLOCKS, 9, 12, 0xABCDEF01, 0x55AA)

    read = decode_superblock(encode_superblock(written, store), slot_of(GENERATION), store)

    assert slot_of(GENERATION) == 1 and slot_of(GENERATION + 1) == 0
    assert vars(read) == vars(written)
    assert len(encode_superblock(written, store)) == layout.BLOCK_BYTES


@pytest.mark.parametrize(
    ("offset", "width", "value", "code"),
    [patch[1:] for patch in SUPERBLOCK_PATCHES],
    ids=[patch[0] for patch in SUPERBLOCK_PATCHES],
)
def test_superblock_with_an_impossible_field_is_refused_even_with_a_valid_checksum(
    offset: int, width: int, value: int, code: int
) -> None:
    store = fresh_store()
    patch_superblock(store, FIRST_SLOT, offset, width, value)

    assert code_of(decode_superblock, store.read(FIRST_SLOT), FIRST_SLOT, store) == code


def test_superblock_with_a_wrong_checksum_or_no_magic_is_refused() -> None:
    store = fresh_store()
    flip_byte(store, FIRST_SLOT, layout.SUPERBLOCK_VOLUME)

    assert code_of(decode_superblock, store.read(FIRST_SLOT), FIRST_SLOT, store) == CORRUPTED
    assert code_of(decode_superblock, bytes(layout.BLOCK_BYTES), FIRST_SLOT, store) == CORRUPTED


def test_metadata_block_round_trips_with_its_type_and_generation() -> None:
    block = encode_block(layout.DIRECTORY_MAGIC, 4, b"payload")

    assert decode_block(block, layout.DIRECTORY_MAGIC, 4) == (4, b"payload")
    assert decode_block(block, layout.DIRECTORY_MAGIC, 9) == (4, b"payload")
    assert len(block) == layout.BLOCK_BYTES


def test_metadata_block_is_refused_by_type_generation_and_shape() -> None:
    block = encode_block(layout.DIRECTORY_MAGIC, 4, b"payload")
    with_tail = block[:-1] + b"\x01"
    oversized = block[:4] + (layout.PAYLOAD_BYTES + 1).to_bytes(4, "little") + block[8:]
    unborn = encode_block(layout.DIRECTORY_MAGIC, 0, b"payload")

    assert code_of(decode_block, block, layout.INDEX_MAGIC, 4) == CORRUPTED
    assert code_of(decode_block, block, layout.DIRECTORY_MAGIC, 3) == CORRUPTED
    assert code_of(decode_block, unborn, layout.DIRECTORY_MAGIC, 4) == CORRUPTED
    assert code_of(decode_block, with_tail, layout.DIRECTORY_MAGIC, 4) == CORRUPTED
    assert code_of(decode_block, oversized, layout.DIRECTORY_MAGIC, 4) == CORRUPTED
    assert code_of(decode_block, block[:-1], layout.DIRECTORY_MAGIC, 4) == CORRUPTED
    assert (
        code_of(encode_block, layout.INDEX_MAGIC, 1, bytes(layout.PAYLOAD_BYTES + 1))
        == LIMIT_EXCEEDED
    )


def test_directory_entries_round_trip_in_name_order() -> None:
    entries = {b"b": entry(layout.KIND_DIRECTORY), b"a": entry(size=300), b"c": entry()}

    payload = encode_entries(entries)
    decoded = decode_entries(payload)

    assert list(decoded) == [b"a", b"b", b"c"]
    assert vars(decoded[b"a"]) == vars(entries[b"a"])
    assert decoded[b"b"].kind == layout.KIND_DIRECTORY


def test_directory_payload_with_a_broken_entry_is_refused() -> None:
    first = encode_entry(b"a", entry())
    second = encode_entry(b"b", entry())
    reserved = bytearray(first)
    reserved[layout.ENTRY_RESERVED] = 1
    damaged = [
        second + first,
        first + first,
        first + second[:-1],
        first + second[:10],
        bytes(reserved),
        encode_entry(b"a/b", entry()),
        encode_entry(b"..", entry()),
        encode_entry(b"a", entry(layout.KIND_DIRECTORY, 1)),
        encode_entry(b"a", entry(3)),
        encode_entry(b"a", entry(size=layout.MAX_FILE_BYTES + 1)),
    ]

    for payload in damaged:
        assert code_of(decode_entries, payload) == CORRUPTED


def test_file_index_round_trips_with_holes() -> None:
    block_map = BlockMap()
    block_map.resize(3)
    block_map.blocks[0], block_map.checksums[0] = 9, 0x11
    block_map.blocks[2], block_map.checksums[2] = 12, 0x33

    decoded = decode_index(encode_index(block_map), 3)

    assert decoded.blocks == [9, layout.NO_BLOCK, 12]
    assert decoded.checksums == [0x11, 0, 0x33]
    assert decoded.allocated() == [9, 12]


def test_file_index_that_does_not_fit_its_file_is_refused() -> None:
    block_map = BlockMap()
    block_map.resize(2)
    payload = encode_index(block_map)
    unknown_level = b"\x01" + payload[1:]
    hole_with_checksum = payload[: layout.INDEX_PREFIX_BYTES + 4] + b"\x01" + payload[13:]

    assert code_of(decode_index, payload, 3) == CORRUPTED
    assert code_of(decode_index, payload, 1) == CORRUPTED
    assert code_of(decode_index, unknown_level, 2) == CORRUPTED
    assert code_of(decode_index, hole_with_checksum, 2) == CORRUPTED


def test_largest_file_fits_in_one_index_block() -> None:
    assert layout.INDEX_FANOUT * layout.POINTER_BYTES + layout.INDEX_PREFIX_BYTES <= (
        layout.PAYLOAD_BYTES
    )
    assert layout.MAX_FILE_BYTES == layout.INDEX_FANOUT * layout.BLOCK_BYTES


@pytest.mark.parametrize(("text", "valid"), UTF8_SAMPLES)
def test_only_well_formed_utf8_is_accepted(text: bytes, valid: bool) -> None:
    assert is_utf8(text) is valid
    assert is_utf8(text) is _decodes(text)


def test_names_are_bounded_and_never_special() -> None:
    assert name_is_valid(b"n" * layout.MAX_NAME_BYTES)
    for name in (b"", b".", b"..", b"a/b", b"a\x00b", b"n" * (layout.MAX_NAME_BYTES + 1), b"\xff"):
        assert not name_is_valid(name)
        assert code_of(check_name, name) == INVALID_ARGUMENT


def _decodes(text: bytes) -> bool:
    try:
        text.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True
