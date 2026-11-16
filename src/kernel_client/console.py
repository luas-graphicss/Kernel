from kernel_client import services
from kernel_client.processes import clock
from kernel_protocol.services.console import (
    MAX_WRITE_BYTES,
    OPERATION_READ_LINE,
    OPERATION_WRITE,
    decode_count,
    encode_timeout,
)
from kernel_protocol.syscalls.numbers import DEADLINE_NEVER


def write(endpoint: int, data: bytes, timeout_nanoseconds: int) -> None:
    deadline = clock() + timeout_nanoseconds
    sent = 0
    while sent < len(data):
        chunk = data[sent : sent + MAX_WRITE_BYTES]
        payload, _received = services.call(endpoint, OPERATION_WRITE, chunk, deadline=deadline)
        sent += decode_count(payload)


def read_line(endpoint: int, timeout_nanoseconds: int = DEADLINE_NEVER) -> bytes:
    payload, _received = services.call(
        endpoint, OPERATION_READ_LINE, encode_timeout(timeout_nanoseconds)
    )
    return payload
