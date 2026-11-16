import _probe

from kernel_protocol.syscalls.numbers import BUFFER_MAP, IPC_CALL

WORD_BYTES = 8
MAPPING_BYTES = 16
BYTE_ORDER = "little"


def call(number: int, *arguments: int) -> int:
    return _probe.syscall(number, *arguments)


def word(value: int) -> bytes:
    return value.to_bytes(WORD_BYTES, BYTE_ORDER)


def read_word(buffer, offset: int) -> int:
    return int.from_bytes(buffer[offset : offset + WORD_BYTES], BYTE_ORDER)


def map_buffer(handle: int, rights: int) -> tuple[int, int, int]:
    description = bytearray(MAPPING_BYTES)
    status = _probe.syscall(BUFFER_MAP, handle, rights, _probe.address(description))
    return status, read_word(description, 0), read_word(description, WORD_BYTES)


def call_into(
    endpoint: int,
    message: bytes,
    response_address: int,
    capacity: int,
    transfer: int,
    deadline: int,
) -> int:
    control = bytearray(word(deadline) + word(transfer) + word(0))
    return _probe.syscall(
        IPC_CALL,
        endpoint,
        _probe.address(message),
        len(message),
        response_address,
        capacity,
        _probe.address(control),
    )
