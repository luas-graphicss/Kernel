import struct
from dataclasses import dataclass

from kernel_tool.outcome import CheckError

MAGIC = b"KUIM"
VERSION = 2
HEADER = struct.Struct("<4sIQQQQQQQQ")
LOAD_BASE = struct.Struct("<Q")
LOAD_BASE_OFFSET = 8
GUARD_BYTES = 4096


@dataclass(frozen=True, slots=True)
class UserImageHeader:
    load_base: int
    file_bytes: int
    entry: int
    text_bytes: int
    rodata_bytes: int
    data_bytes: int
    heap_bytes: int
    stack_bytes: int

    @property
    def memory_bytes(self) -> int:
        return (
            self.text_bytes
            + self.rodata_bytes
            + self.data_bytes
            + self.heap_bytes
            + GUARD_BYTES
            + self.stack_bytes
        )


def read_header(image: bytes) -> UserImageHeader:
    if len(image) < HEADER.size:
        raise CheckError(f"user image has {len(image)} bytes; its header needs {HEADER.size}")
    magic, version, *fields = HEADER.unpack_from(image)
    if magic != MAGIC or version != VERSION:
        raise CheckError(f"user image has magic {magic!r} and version {version}")
    return UserImageHeader(*fields)


def with_load_base(image: bytes, load_base: int) -> bytes:
    read_header(image)
    patched = bytearray(image)
    LOAD_BASE.pack_into(patched, LOAD_BASE_OFFSET, load_base)
    return bytes(patched)
