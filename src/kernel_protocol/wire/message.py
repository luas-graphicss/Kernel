from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    UNSUPPORTED,
    KernelError,
)

VERSION = 1
HEADER_BYTES = 24
MAX_PAYLOAD_BYTES = 4096
FLAG_REPLY = 1
FLAG_ERROR = 2
KNOWN_FLAGS = FLAG_REPLY | FLAG_ERROR
MAX_OPERATION = 0xFFFFFFFF
MAX_CORRELATION = 0xFFFFFFFFFFFFFFFF
RESERVED_FIELD = b"\x00\x00\x00\x00"


class Message:
    def __init__(self, operation: int, flags: int, correlation: int, payload: bytes) -> None:
        self.operation = operation
        self.flags = flags
        self.correlation = correlation
        self.payload = payload


def pack_unsigned(value: int, width: int) -> bytes:
    return value.to_bytes(width, "little")


def unpack_unsigned(buffer: bytes, start: int, end: int) -> int:
    return int.from_bytes(buffer[start:end], "little")


def flags_are_valid(flags: int) -> bool:
    if flags & ~KNOWN_FLAGS:
        return False
    return not (flags & FLAG_ERROR and not flags & FLAG_REPLY)


def encode_message(message: Message) -> bytes:
    if message.operation < 0 or message.operation > MAX_OPERATION:
        raise KernelError(INVALID_ARGUMENT, "operation does not fit in 32 bits")
    if message.correlation < 0 or message.correlation > MAX_CORRELATION:
        raise KernelError(INVALID_ARGUMENT, "correlation does not fit in 64 bits")
    if not flags_are_valid(message.flags):
        raise KernelError(INVALID_ARGUMENT, "unknown or inconsistent flags")
    if len(message.payload) > MAX_PAYLOAD_BYTES:
        raise KernelError(MESSAGE_TOO_LARGE, "payload exceeds the inline limit")
    return (
        pack_unsigned(VERSION, 2)
        + pack_unsigned(message.flags, 2)
        + pack_unsigned(message.operation, 4)
        + pack_unsigned(len(message.payload), 4)
        + RESERVED_FIELD
        + pack_unsigned(message.correlation, 8)
        + message.payload
    )


def decode_message(buffer: bytes) -> Message:
    if len(buffer) < HEADER_BYTES:
        raise KernelError(INVALID_ARGUMENT, "message is shorter than its header")
    if unpack_unsigned(buffer, 0, 2) != VERSION:
        raise KernelError(UNSUPPORTED, "unknown message version")
    flags = unpack_unsigned(buffer, 2, 4)
    if not flags_are_valid(flags) or buffer[12:16] != RESERVED_FIELD:
        raise KernelError(INVALID_ARGUMENT, "unknown flags or reserved field in use")
    payload_bytes = unpack_unsigned(buffer, 8, 12)
    if payload_bytes > MAX_PAYLOAD_BYTES:
        raise KernelError(MESSAGE_TOO_LARGE, "payload exceeds the inline limit")
    if len(buffer) != HEADER_BYTES + payload_bytes:
        raise KernelError(INVALID_ARGUMENT, "message length does not match its header")
    return Message(
        operation=unpack_unsigned(buffer, 4, 8),
        flags=flags,
        correlation=unpack_unsigned(buffer, 16, 24),
        payload=bytes(buffer[HEADER_BYTES:]),
    )
