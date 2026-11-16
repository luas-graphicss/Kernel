from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import pack_unsigned, unpack_unsigned

OPERATION_READ = 16

MAX_READ_BYTES = 256
COUNT_BYTES = 4


def encode_count(count: int) -> bytes:
    return pack_unsigned(count, COUNT_BYTES)


def decode_count(payload: bytes) -> int:
    if len(payload) != COUNT_BYTES:
        raise KernelError(INVALID_ARGUMENT, "entropy count has the wrong size")
    count = unpack_unsigned(payload, 0, COUNT_BYTES)
    if count < 1 or count > MAX_READ_BYTES:
        raise KernelError(INVALID_ARGUMENT, "entropy request outside one transfer")
    return count
