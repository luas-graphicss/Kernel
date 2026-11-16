import _probe

from kernel_client import ipc
from kernel_client.processes import Startup
from kernel_protocol.wire.message import Message

SPINNING_OPERATION = 1
NO_FLAGS = 0


def main() -> bool:
    ipc.send(Startup().handles[0], Message(SPINNING_OPERATION, NO_FLAGS, 0, b""))
    _probe.spin()
    return False
