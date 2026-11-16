import struct
from dataclasses import dataclass

from kernel_tool.outcome import CheckError

MAGIC = b"KUIM"
VERSION = 1
HEADER = struct.Struct("<4sIQQQQQQ")
LOAD_BASE = struct.Struct("<Q")
LOAD_BASE_OFFSET = 8


@dataclass(frozen=True, slots=True)
class UserImageHeader:
    load_base: int
    file_bytes: int
    memory_bytes: int
    entry: int
    heap_bytes: int
    stack_bytes: int


def read_header(image: bytes) -> UserImageHeader:
    if len(image) < HEADER.size:
        raise CheckError(f"user image has {len(image)} bytes; its header needs {HEADER.size}")
    magic, version, load_base, file_bytes, memory_bytes, entry, heap_bytes, stack_bytes = (
        HEADER.unpack_from(image)
    )
    if magic != MAGIC or version != VERSION:
        raise CheckError(f"user image has magic {magic!r} and version {version}")
    return UserImageHeader(load_base, file_bytes, memory_bytes, entry, heap_bytes, stack_bytes)


def with_load_base(image: bytes, load_base: int) -> bytes:
    read_header(image)
    patched = bytearray(image)
    LOAD_BASE.pack_into(patched, LOAD_BASE_OFFSET, load_base)
    return bytes(patched)
