from kernel_client import ipc
from kernel_client.processes import Startup
from suites.scheduling.protocol import OPERATION_REQUEST, announce, plain

LINKED_HANDLES = 2


def main() -> bool:
    handles = Startup().handles
    announce(handles[0])
    if len(handles) == LINKED_HANDLES:
        ipc.call(handles[1], plain(OPERATION_REQUEST))
    ipc.receive(ipc.create_endpoint())
    return False
