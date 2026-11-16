from kernel_client import ipc, memory
from kernel_client.processes import Startup
from kernel_protocol.wire.message import Message
from suites.support.layout import PAGE_BYTES

BUFFER_OPERATION = 1
NO_FLAGS = 0


def main() -> bool:
    buffer = memory.create_buffer(PAGE_BYTES)
    ipc.send(Startup().handles[0], Message(BUFFER_OPERATION, NO_FLAGS, 0, b""), buffer)
    ipc.receive(ipc.create_endpoint())
    return False
