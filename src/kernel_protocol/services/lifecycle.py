from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import pack_unsigned, unpack_unsigned

OPERATION_REGISTER = 1
OPERATION_STOP = 2
FIRST_SERVICE_OPERATION = 16

IDENTITY_BYTES = 8
ERROR_BYTES = 4


def encode_supervisor(identity: int, role: bytes = b"") -> bytes:
    return pack_unsigned(identity, IDENTITY_BYTES) + role


def decode_supervisor(argument: bytes) -> tuple[int, bytes]:
    if len(argument) < IDENTITY_BYTES:
        raise KernelError(INVALID_ARGUMENT, "service started without its supervisor identity")
    return unpack_unsigned(argument, 0, IDENTITY_BYTES), argument[IDENTITY_BYTES:]


def encode_error(code: int) -> bytes:
    return pack_unsigned(code, ERROR_BYTES)


def decode_error(payload: bytes) -> int:
    if len(payload) != ERROR_BYTES:
        return INVALID_ARGUMENT
    return unpack_unsigned(payload, 0, ERROR_BYTES) or INVALID_ARGUMENT
