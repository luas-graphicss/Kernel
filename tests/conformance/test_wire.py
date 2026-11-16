import pytest

from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    UNSUPPORTED,
    KernelError,
)
from kernel_protocol.wire.message import (
    FLAG_ERROR,
    FLAG_REPLY,
    HEADER_BYTES,
    MAX_PAYLOAD_BYTES,
    Message,
    decode_message,
    encode_message,
)

REFERENCE_MESSAGE = Message(
    operation=0x01020304,
    flags=FLAG_REPLY,
    correlation=0x1112131415161718,
    payload=b"ping",
)
REFERENCE_BYTES = bytes.fromhex("01000100040302010400000000000000181716151413121170696e67")


def decode_error(buffer: bytes) -> int:
    with pytest.raises(KernelError) as raised:
        decode_message(buffer)
    return raised.value.code


def encode_error(message: Message) -> int:
    with pytest.raises(KernelError) as raised:
        encode_message(message)
    return raised.value.code


def test_encoding_matches_the_documented_layout() -> None:
    assert encode_message(REFERENCE_MESSAGE) == REFERENCE_BYTES


def test_decoding_restores_every_field() -> None:
    decoded = decode_message(REFERENCE_BYTES)

    assert decoded.operation == REFERENCE_MESSAGE.operation
    assert decoded.flags == REFERENCE_MESSAGE.flags
    assert decoded.correlation == REFERENCE_MESSAGE.correlation
    assert decoded.payload == REFERENCE_MESSAGE.payload


def test_largest_payload_round_trips() -> None:
    payload = bytes(range(256)) * (MAX_PAYLOAD_BYTES // 256)
    message = Message(operation=1, flags=0, correlation=0, payload=payload)

    assert decode_message(encode_message(message)).payload == payload


def with_bytes(offset: int, replacement: bytes) -> bytes:
    return REFERENCE_BYTES[:offset] + replacement + REFERENCE_BYTES[offset + len(replacement) :]


@pytest.mark.parametrize(
    ("buffer", "code"),
    [
        (REFERENCE_BYTES[: HEADER_BYTES - 1], INVALID_ARGUMENT),
        (with_bytes(0, b"\x02\x00"), UNSUPPORTED),
        (with_bytes(2, b"\x04\x00"), INVALID_ARGUMENT),
        (with_bytes(2, b"\x02\x00"), INVALID_ARGUMENT),
        (with_bytes(12, b"\x01\x00\x00\x00"), INVALID_ARGUMENT),
        (with_bytes(8, b"\x01\x10\x00\x00"), MESSAGE_TOO_LARGE),
        (REFERENCE_BYTES + b"\x00", INVALID_ARGUMENT),
        (REFERENCE_BYTES[:-1], INVALID_ARGUMENT),
    ],
    ids=[
        "short-header",
        "unknown-version",
        "unknown-flag",
        "error-without-reply",
        "reserved-in-use",
        "payload-over-limit",
        "trailing-byte",
        "truncated-payload",
    ],
)
def test_malformed_messages_are_rejected(buffer: bytes, code: int) -> None:
    assert decode_error(buffer) == code


def test_version_is_checked_before_flags_and_length() -> None:
    unknown_version = with_bytes(0, b"\x09\x00")
    also_bad_flags = unknown_version[:2] + b"\xff\xff" + unknown_version[4:]

    assert decode_error(also_bad_flags + b"trailing") == UNSUPPORTED


@pytest.mark.parametrize(
    ("message", "code"),
    [
        (Message(operation=-1, flags=0, correlation=0, payload=b""), INVALID_ARGUMENT),
        (Message(operation=1 << 32, flags=0, correlation=0, payload=b""), INVALID_ARGUMENT),
        (Message(operation=1, flags=0, correlation=1 << 64, payload=b""), INVALID_ARGUMENT),
        (Message(operation=1, flags=FLAG_ERROR, correlation=0, payload=b""), INVALID_ARGUMENT),
        (
            Message(operation=1, flags=0, correlation=0, payload=bytes(MAX_PAYLOAD_BYTES + 1)),
            MESSAGE_TOO_LARGE,
        ),
    ],
    ids=["negative-operation", "wide-operation", "wide-correlation", "bad-flags", "payload"],
)
def test_encoding_rejects_fields_outside_the_format(message: Message, code: int) -> None:
    assert encode_error(message) == code
