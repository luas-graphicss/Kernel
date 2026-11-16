from kernel_client import ipc
from kernel_protocol.wire.message import Message

NO_FLAGS = 0
OPERATION_READY = 1
OPERATION_WINDOW = 2
OPERATION_REPORT = 3
OPERATION_REQUEST = 4
OPERATION_NOTE = 5
OPERATION_STOP = 6


def plain(operation: int, correlation: int = 0, payload: bytes = b"") -> Message:
    return Message(operation, NO_FLAGS, correlation, payload)


def announce(reports: int) -> int:
    endpoint = ipc.create_endpoint()
    ipc.send(reports, plain(OPERATION_READY), endpoint)
    return endpoint
