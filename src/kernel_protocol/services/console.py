from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import pack_unsigned, unpack_unsigned

OPERATION_WRITE = 16
OPERATION_READ_LINE = 17

MAX_WRITE_BYTES = 1024
MAX_LINE_BYTES = 255
MAX_PENDING_LINES = 4
COUNT_BYTES = 4
TIMEOUT_BYTES = 8


def encode_count(count: int) -> bytes:
    return pack_unsigned(count, COUNT_BYTES)


def decode_count(payload: bytes) -> int:
    if len(payload) != COUNT_BYTES:
        raise KernelError(INVALID_ARGUMENT, "console count has the wrong size")
    return unpack_unsigned(payload, 0, COUNT_BYTES)


def encode_timeout(nanoseconds: int) -> bytes:
    return pack_unsigned(nanoseconds, TIMEOUT_BYTES)


def decode_timeout(payload: bytes) -> int:
    if len(payload) != TIMEOUT_BYTES:
        raise KernelError(INVALID_ARGUMENT, "console timeout has the wrong size")
    return unpack_unsigned(payload, 0, TIMEOUT_BYTES)
