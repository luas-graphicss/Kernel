from kernel_client import services
from kernel_protocol.errors.codes import IO_ERROR, KernelError
from kernel_protocol.services.entropy import MAX_READ_BYTES, OPERATION_READ, encode_count

MAX_ATTEMPTS = 8


def read(endpoint: int, count: int) -> bytes:
    collected = b""
    attempts = 0
    while len(collected) < count:
        if attempts == MAX_ATTEMPTS:
            raise KernelError(IO_ERROR, "the entropy source returned too few bytes")
        missing = count - len(collected)
        wanted = missing if missing < MAX_READ_BYTES else MAX_READ_BYTES
        payload, _received = services.call(endpoint, OPERATION_READ, encode_count(wanted))
        collected += payload
        attempts += 1
    return collected
