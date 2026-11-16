import _process
from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    TIMED_OUT,
    UNSUPPORTED,
)
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER
from kernel_protocol.wire.message import (
    FLAG_ERROR,
    FLAG_REPLY,
    HEADER_BYTES,
    MAX_PAYLOAD_BYTES,
    encode_message,
)
from runtime_selftest.checks import Checks
from suites.ipc.actors import queued_messages
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support.expectations import error_code
from suites.support.reporting import Context

PAYLOAD = b"payload!"
VERSION_OFFSET = 0
FLAGS_OFFSET = 2
PAYLOAD_BYTES_OFFSET = 8
RESERVED_OFFSET = 12
UNKNOWN_VERSION = 2
UNKNOWN_FLAG = 4
NO_TRANSFER = 0
SHORT_WAIT_NANOSECONDS = 2000000
SINGLE_BYTE_CHANGES = (
    ("an unknown version", VERSION_OFFSET, UNKNOWN_VERSION, UNSUPPORTED),
    ("an unknown flag", FLAGS_OFFSET, UNKNOWN_FLAG, INVALID_ARGUMENT),
    ("the error flag without the reply flag", FLAGS_OFFSET, FLAG_ERROR, INVALID_ARGUMENT),
    ("the reply flag outside a reply", FLAGS_OFFSET, FLAG_REPLY, INVALID_ARGUMENT),
    ("a reserved field in use", RESERVED_OFFSET, 1, INVALID_ARGUMENT),
    (
        "a payload longer than what was sent",
        PAYLOAD_BYTES_OFFSET,
        len(PAYLOAD) + 1,
        INVALID_ARGUMENT,
    ),
    (
        "a payload shorter than what was sent",
        PAYLOAD_BYTES_OFFSET,
        len(PAYLOAD) - 1,
        INVALID_ARGUMENT,
    ),
)


def malformed_messages() -> list[tuple[str, bytes, int]]:
    valid = encode_message(plain(OPERATION_REQUEST, 9, PAYLOAD))
    messages = [("a truncated header", valid[: HEADER_BYTES - 1], INVALID_ARGUMENT)]
    for description, offset, value, code in SINGLE_BYTE_CHANGES:
        changed = bytearray(valid)
        changed[offset] = value
        messages.append((description, bytes(changed), code))
    declared = (MAX_PAYLOAD_BYTES + 1).to_bytes(RESERVED_OFFSET - PAYLOAD_BYTES_OFFSET, "little")
    oversized = valid[:PAYLOAD_BYTES_OFFSET] + declared + valid[RESERVED_OFFSET:]
    messages.append(("a declared payload above the limit", oversized, MESSAGE_TOO_LARGE))
    messages.append(
        (
            "more bytes than a message can hold",
            oversized + bytes(MAX_PAYLOAD_BYTES + 1 - len(PAYLOAD)),
            MESSAGE_TOO_LARGE,
        )
    )
    return messages


def run(context: Context, checks: Checks) -> None:
    endpoint = ipc.create_endpoint()
    before = system.counters(context.system)
    for description, message, code in malformed_messages():
        checks.require(
            _process.send(endpoint, message, NO_TRANSFER, DEADLINE_NEVER) == -code,
            f"a message with {description} is refused",
        )
    checks.require(queued_messages(context, before) == 0, "a refused message is never queued")
    checks.require(
        error_code(ipc.receive, endpoint, processes.clock() + SHORT_WAIT_NANOSECONDS) == TIMED_OUT,
        "the endpoint stays empty",
    )
    largest = plain(OPERATION_REQUEST, 1, bytes(MAX_PAYLOAD_BYTES))
    ipc.send(endpoint, largest)
    checks.require(
        len(ipc.receive(endpoint).message.payload) == MAX_PAYLOAD_BYTES,
        "the largest valid message is delivered whole",
    )
    capabilities.close(endpoint)
