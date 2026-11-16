from kernel_services.filesystem.format.codec import corrupted, get, put
from kernel_services.filesystem.format.layout import (
    ENTRY_BLOCK,
    ENTRY_CHECKSUM,
    ENTRY_FIXED_BYTES,
    ENTRY_NAME_LENGTH,
    ENTRY_NODE,
    ENTRY_RESERVED,
    ENTRY_SIZE,
    KIND_DIRECTORY,
    KIND_FILE,
    MAX_FILE_BYTES,
)
from kernel_services.filesystem.format.names import name_is_valid


class Entry:
    def __init__(self, kind: int, node: int, block: int, checksum: int, size: int) -> None:
        self.kind = kind
        self.node = node
        self.block = block
        self.checksum = checksum
        self.size = size


def entry_bytes(name: bytes) -> int:
    return ENTRY_FIXED_BYTES + len(name)


def encode_entry(name: bytes, entry: Entry) -> bytes:
    return (
        put(entry.kind, 1)
        + put(len(name), 1)
        + bytes(2)
        + put(entry.block, 4)
        + put(entry.checksum, 4)
        + put(entry.node, 8)
        + put(entry.size, 8)
        + name
    )


def encode_entries(entries: dict[bytes, Entry]) -> bytes:
    return b"".join([encode_entry(name, entries[name]) for name in sorted(entries)])


def decode_entry(payload: bytes, offset: int) -> tuple[bytes, Entry]:
    name_length = payload[offset + ENTRY_NAME_LENGTH]
    name = payload[offset + ENTRY_FIXED_BYTES : offset + ENTRY_FIXED_BYTES + name_length]
    entry = Entry(
        kind=payload[offset],
        node=get(payload, offset + ENTRY_NODE, 8),
        block=get(payload, offset + ENTRY_BLOCK, 4),
        checksum=get(payload, offset + ENTRY_CHECKSUM, 4),
        size=get(payload, offset + ENTRY_SIZE, 8),
    )
    if len(name) != name_length or not name_is_valid(name):
        raise corrupted("directory entry has a truncated or invalid name")
    if get(payload, offset + ENTRY_RESERVED, 2) != 0:
        raise corrupted("directory entry uses a reserved field")
    if entry.kind == KIND_DIRECTORY and entry.size != 0:
        raise corrupted("directory entry gives a size to a directory")
    if entry.kind not in (KIND_FILE, KIND_DIRECTORY) or entry.size > MAX_FILE_BYTES:
        raise corrupted("directory entry has an unknown kind or an impossible size")
    return name, entry


def decode_entries(payload: bytes) -> dict[bytes, Entry]:
    entries: dict[bytes, Entry] = {}
    previous = b""
    offset = 0
    while offset < len(payload):
        if offset + ENTRY_FIXED_BYTES > len(payload):
            raise corrupted("directory ends inside an entry")
        name, entry = decode_entry(payload, offset)
        if name <= previous:
            raise corrupted("directory names are repeated or out of order")
        entries[name] = entry
        previous = name
        offset += entry_bytes(name)
    return entries
