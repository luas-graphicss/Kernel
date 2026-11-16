from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import MAX_PAYLOAD_BYTES, pack_unsigned, unpack_unsigned

OPERATION_ROOT = 16
OPERATION_EVICT = 17
OPERATION_ENTER = 18
OPERATION_LEAVE = 19
OPERATION_SUBSPACE = 20
OPERATION_DROP = 21
OPERATION_STATUS = 22
OPERATION_OPEN = 23
OPERATION_CLOSE = 24
OPERATION_READ = 25
OPERATION_WRITE = 26
OPERATION_TRUNCATE = 27
OPERATION_SYNC = 28
OPERATION_STAT = 29
OPERATION_LIST = 30
OPERATION_MAKE_DIRECTORY = 31
OPERATION_REMOVE = 32
OPERATION_RENAME = 33

OPEN_READ = 0x01
OPEN_WRITE = 0x02
OPEN_CREATE = 0x04
OPEN_EXCLUSIVE = 0x08
OPEN_TRUNCATE = 0x10
OPEN_DIRECTORY = 0x20
OPEN_KNOWN = 0x3F

NAMESPACE_READ = 0x1
NAMESPACE_WRITE = 0x2
NAMESPACE_DELEGATE = 0x4
NAMESPACE_ALL = 0x7

KIND_FILE = 1
KIND_DIRECTORY = 2

MODE_READ_ONLY = 0
MODE_READ_WRITE = 1

MAX_PATH_BYTES = 1024
MAX_PATH_COMPONENTS = 32
MAX_TRANSFER_BYTES = MAX_PAYLOAD_BYTES - 64
LIST_END = 0xFFFFFFFF

SUBJECT_BYTES = 16
SESSION_BYTES = 20
OPENED_BYTES = 20
EXTENT_BYTES = 12
STAT_BYTES = 12
ENTRY_FIXED_BYTES = 10
MOUNT_FIXED_BYTES = 22


class MountReport:
    def __init__(
        self,
        name: bytes,
        code: int,
        mode: int,
        reason: bytes,
        generation: int,
        free_blocks: int,
        total_blocks: int,
    ) -> None:
        self.name = name
        self.code = code
        self.mode = mode
        self.reason = reason
        self.generation = generation
        self.free_blocks = free_blocks
        self.total_blocks = total_blocks


def malformed() -> KernelError:
    return KernelError(INVALID_ARGUMENT, "file request does not have the layout of its operation")


def exactly(payload: bytes, size: int) -> bytes:
    if len(payload) != size:
        raise malformed()
    return payload


def at_least(payload: bytes, size: int) -> bytes:
    if len(payload) < size:
        raise malformed()
    return payload


def encode_request(instance: int, subject: int, body: bytes = b"") -> bytes:
    return pack_unsigned(instance, 8) + pack_unsigned(subject, 8) + body


def decode_request(payload: bytes) -> tuple[int, int, bytes]:
    at_least(payload, SUBJECT_BYTES)
    return (
        unpack_unsigned(payload, 0, 8),
        unpack_unsigned(payload, 8, 16),
        payload[SUBJECT_BYTES:],
    )


def encode_session(instance: int, session: int, rights: int) -> bytes:
    return pack_unsigned(instance, 8) + pack_unsigned(session, 8) + pack_unsigned(rights, 4)


def decode_session(payload: bytes) -> tuple[int, int, int]:
    exactly(payload, SESSION_BYTES)
    return (
        unpack_unsigned(payload, 0, 8),
        unpack_unsigned(payload, 8, 16),
        unpack_unsigned(payload, 16, 20),
    )


def encode_tagged_path(tag: int, path: bytes) -> bytes:
    return pack_unsigned(tag, 4) + path


def decode_tagged_path(body: bytes) -> tuple[int, bytes]:
    at_least(body, 4)
    return unpack_unsigned(body, 0, 4), body[4:]


def encode_opened(handle: int, kind: int, size: int) -> bytes:
    return pack_unsigned(handle, 8) + pack_unsigned(kind, 4) + pack_unsigned(size, 8)


def decode_opened(payload: bytes) -> tuple[int, int, int]:
    exactly(payload, OPENED_BYTES)
    return (
        unpack_unsigned(payload, 0, 8),
        unpack_unsigned(payload, 8, 12),
        unpack_unsigned(payload, 12, 20),
    )


def encode_extent(offset: int, count: int) -> bytes:
    return pack_unsigned(offset, 8) + pack_unsigned(count, 4)


def decode_extent(body: bytes) -> tuple[int, int]:
    exactly(body, EXTENT_BYTES)
    return unpack_unsigned(body, 0, 8), unpack_unsigned(body, 8, 12)


def encode_write(offset: int, data: bytes) -> bytes:
    return pack_unsigned(offset, 8) + data


def decode_write(body: bytes) -> tuple[int, bytes]:
    at_least(body, 8)
    return unpack_unsigned(body, 0, 8), body[8:]


def encode_size(size: int) -> bytes:
    return pack_unsigned(size, 8)


def decode_size(body: bytes) -> int:
    return unpack_unsigned(exactly(body, 8), 0, 8)


def encode_count(count: int) -> bytes:
    return pack_unsigned(count, 4)


def decode_count(body: bytes) -> int:
    return unpack_unsigned(exactly(body, 4), 0, 4)


def encode_stat(kind: int, size: int) -> bytes:
    return pack_unsigned(kind, 4) + pack_unsigned(size, 8)


def decode_stat(payload: bytes) -> tuple[int, int]:
    exactly(payload, STAT_BYTES)
    return unpack_unsigned(payload, 0, 4), unpack_unsigned(payload, 4, 12)


def encode_rename(source: bytes, target: bytes) -> bytes:
    return pack_unsigned(len(source), 2) + source + target


def decode_rename(body: bytes) -> tuple[bytes, bytes]:
    at_least(body, 2)
    source_end = 2 + unpack_unsigned(body, 0, 2)
    at_least(body, source_end)
    return body[2:source_end], body[source_end:]


def encode_entry(name: bytes, kind: int, size: int) -> bytes:
    return pack_unsigned(kind, 1) + pack_unsigned(len(name), 1) + pack_unsigned(size, 8) + name


def encode_entries(next_cursor: int, entries: list[bytes]) -> bytes:
    return pack_unsigned(next_cursor, 4) + b"".join(entries)


def decode_entries(payload: bytes) -> tuple[int, list[tuple[bytes, int, int]]]:
    at_least(payload, 4)
    entries = []
    offset = 4
    while offset < len(payload):
        at_least(payload, offset + ENTRY_FIXED_BYTES)
        name_end = offset + ENTRY_FIXED_BYTES + payload[offset + 1]
        at_least(payload, name_end)
        size = unpack_unsigned(payload, offset + 2, offset + 10)
        entries.append((payload[offset + ENTRY_FIXED_BYTES : name_end], payload[offset], size))
        offset = name_end
    return unpack_unsigned(payload, 0, 4), entries


def encode_mount(report: MountReport) -> bytes:
    return (
        pack_unsigned(len(report.name), 1)
        + pack_unsigned(len(report.reason), 1)
        + pack_unsigned(report.code, 2)
        + pack_unsigned(report.mode, 2)
        + pack_unsigned(report.generation, 8)
        + pack_unsigned(report.free_blocks, 4)
        + pack_unsigned(report.total_blocks, 4)
        + report.name
        + report.reason
    )


def decode_mounts(payload: bytes) -> list[MountReport]:
    reports = []
    offset = 0
    while offset < len(payload):
        at_least(payload, offset + MOUNT_FIXED_BYTES)
        name_end = offset + MOUNT_FIXED_BYTES + payload[offset]
        reason_end = name_end + payload[offset + 1]
        at_least(payload, reason_end)
        reports.append(
            MountReport(
                name=payload[offset + MOUNT_FIXED_BYTES : name_end],
                code=unpack_unsigned(payload, offset + 2, offset + 4),
                mode=unpack_unsigned(payload, offset + 4, offset + 6),
                reason=payload[name_end:reason_end],
                generation=unpack_unsigned(payload, offset + 6, offset + 14),
                free_blocks=unpack_unsigned(payload, offset + 14, offset + 18),
                total_blocks=unpack_unsigned(payload, offset + 18, offset + 22),
            )
        )
        offset = reason_end
    return reports
