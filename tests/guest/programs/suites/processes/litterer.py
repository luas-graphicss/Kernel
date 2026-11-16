import _probe

from kernel_client import capabilities, ipc, memory
from kernel_client.processes import Startup
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.wire.message import Message
from suites.support.layout import NULL_PAGE, PAGE_BYTES

PENDING_MESSAGES = 10
ENDPOINTS = 3
LITTER_OPERATION = 1
NO_FLAGS = 0


def litter() -> None:
    endpoints = [ipc.create_endpoint() for _ in range(ENDPOINTS)]
    for endpoint in endpoints:
        capabilities.derive(endpoint, RIGHT_SEND)
    for correlation in range(PENDING_MESSAGES):
        ipc.send(endpoints[0], Message(LITTER_OPERATION, NO_FLAGS, correlation, b"litter"))
    memory.Mapping(memory.create_buffer(PAGE_BYTES), True).write(0, b"litter")


def leave() -> bool:
    return True


def fault() -> bool:
    _probe.load(NULL_PAGE)
    return True


def block_in_receive() -> bool:
    ipc.receive(ipc.create_endpoint())
    return False


def block_in_call() -> bool:
    ipc.call(Startup().handles[0], Message(LITTER_OPERATION, NO_FLAGS, 0, b""))
    return False


ENDINGS = {
    b"exit": leave,
    b"fault": fault,
    b"receive": block_in_receive,
    b"call": block_in_call,
}


def main() -> bool:
    litter()
    return ENDINGS[Startup().argument]()
