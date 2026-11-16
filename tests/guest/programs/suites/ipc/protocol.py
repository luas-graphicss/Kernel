from kernel_client import ipc
from kernel_protocol.wire.message import Message

NO_FLAGS = 0
OPERATION_REGISTER = 1
OPERATION_REQUEST = 2
OPERATION_RECEIVED = 3
OPERATION_PROCEED = 4


def plain(operation: int, correlation: int = 0, payload: bytes = b"") -> Message:
    return Message(operation, NO_FLAGS, correlation, payload)


def register(registrations: int) -> int:
    endpoint = ipc.create_endpoint()
    ipc.send(registrations, plain(OPERATION_REGISTER), endpoint)
    return endpoint
