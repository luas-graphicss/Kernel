from kernel_protocol.errors.codes import UNSUPPORTED, KernelError
from kernel_services.filesystem.format.codec import corrupted, get, put
from kernel_services.filesystem.format.names import SEPARATOR, name_is_valid
from kernel_services.filesystem.storage import BlockStore

MAGIC = b"KBOOTIMG"
FORMAT_VERSION = 1
ABI_VERSION = 1
BLOCK_BYTES = 4096
HEADER_BYTES = 64
HEADER_VERSION = 8
HEADER_ABI = 12
HEADER_RUNTIME = 16
HEADER_ENTRIES = 32
HEADER_TABLE_BYTES = 36
HEADER_TABLE_CHECKSUM = 40
HEADER_TOTAL_BLOCKS = 44
HEADER_RESERVED = 48
HEADER_CHECKSUM = 60
RUNTIME_BYTES = 16
RESERVED_BYTES = 12
FIRST_TABLE_BLOCK = 1

ENTRY_FIXED_BYTES = 16
ENTRY_RESERVED = 2
ENTRY_FIRST_BLOCK = 4
ENTRY_SIZE = 8
ENTRY_CHECKSUM = 12
MAX_ENTRIES = 64
MAX_PATH_BYTES = 255
MAX_FILE_BYTES = 262144


class Header:
    def __init__(
        self,
        abi: int,
        runtime: bytes,
        entries: int,
        table_bytes: int,
        table_checksum: int,
        total_blocks: int,
    ) -> None:
        self.abi = abi
        self.runtime = runtime
        self.entries = entries
        self.table_bytes = table_bytes
        self.table_checksum = table_checksum
        self.total_blocks = total_blocks


class Entry:
    def __init__(self, path: bytes, first_block: int, size: int, checksum: int) -> None:
        self.path = path
        self.first_block = first_block
        self.size = size
        self.checksum = checksum


def blocks_for(size: int) -> int:
    return (size + BLOCK_BYTES - 1) // BLOCK_BYTES


def path_is_valid(path: bytes) -> bool:
    if len(path) == 0 or len(path) > MAX_PATH_BYTES:
        return False
    return all(name_is_valid(name) for name in path.split(SEPARATOR))


def encode_header(header: Header, store: BlockStore) -> bytes:
    fields = (
        MAGIC
        + put(FORMAT_VERSION, 4)
        + put(header.abi, 4)
        + header.runtime
        + bytes(RUNTIME_BYTES - len(header.runtime))
        + put(header.entries, 4)
        + put(header.table_bytes, 4)
        + put(header.table_checksum, 4)
        + put(header.total_blocks, 4)
        + bytes(RESERVED_BYTES)
    )
    return fields + put(store.checksum(fields), 4) + bytes(BLOCK_BYTES - HEADER_BYTES)


def decode_header(block: bytes, store: BlockStore) -> Header:
    if block[: len(MAGIC)] != MAGIC:
        raise corrupted("device does not hold a boot image")
    if get(block, HEADER_VERSION, 4) != FORMAT_VERSION:
        raise KernelError(UNSUPPORTED, "boot image uses another format version")
    if store.checksum(block[:HEADER_CHECKSUM]) != get(block, HEADER_CHECKSUM, 4):
        raise corrupted("boot image header does not match its checksum")
    if block[HEADER_RESERVED:HEADER_CHECKSUM] != bytes(RESERVED_BYTES):
        raise corrupted("boot image header uses a reserved field")
    return Header(
        abi=get(block, HEADER_ABI, 4),
        runtime=block[HEADER_RUNTIME : HEADER_RUNTIME + RUNTIME_BYTES].rstrip(b"\x00"),
        entries=get(block, HEADER_ENTRIES, 4),
        table_bytes=get(block, HEADER_TABLE_BYTES, 4),
        table_checksum=get(block, HEADER_TABLE_CHECKSUM, 4),
        total_blocks=get(block, HEADER_TOTAL_BLOCKS, 4),
    )


def check_compatibility(header: Header, runtime: bytes) -> None:
    if header.abi != ABI_VERSION:
        raise KernelError(UNSUPPORTED, "boot image was built for another system interface")
    if header.runtime != runtime:
        raise KernelError(UNSUPPORTED, "boot image was built for another Python runtime")


def encode_entry(entry: Entry) -> bytes:
    return (
        put(len(entry.path), 2)
        + bytes(2)
        + put(entry.first_block, 4)
        + put(entry.size, 4)
        + put(entry.checksum, 4)
        + entry.path
    )


def encode_table(entries: list[Entry]) -> bytes:
    return b"".join([encode_entry(entry) for entry in entries])


def decode_entry(table: bytes, offset: int) -> Entry:
    if offset + ENTRY_FIXED_BYTES > len(table):
        raise corrupted("boot image table ends inside an entry")
    path_end = offset + ENTRY_FIXED_BYTES + get(table, offset, 2)
    entry = Entry(
        path=table[offset + ENTRY_FIXED_BYTES : path_end],
        first_block=get(table, offset + ENTRY_FIRST_BLOCK, 4),
        size=get(table, offset + ENTRY_SIZE, 4),
        checksum=get(table, offset + ENTRY_CHECKSUM, 4),
    )
    if path_end > len(table) or not path_is_valid(entry.path):
        raise corrupted("boot image entry has a truncated or invalid path")
    if get(table, offset + ENTRY_RESERVED, 2) != 0 or entry.size > MAX_FILE_BYTES:
        raise corrupted("boot image entry uses a reserved field or an impossible size")
    return entry


def decode_table(table: bytes, count: int) -> list[Entry]:
    entries: list[Entry] = []
    previous = b""
    offset = 0
    if count > MAX_ENTRIES:
        raise corrupted("boot image lists more files than the format allows")
    for _index in range(count):
        entry = decode_entry(table, offset)
        if entry.path <= previous:
            raise corrupted("boot image paths are repeated or out of order")
        entries.append(entry)
        previous = entry.path
        offset += ENTRY_FIXED_BYTES + len(entry.path)
    if offset != len(table):
        raise corrupted("boot image table carries data after its entries")
    return entries
