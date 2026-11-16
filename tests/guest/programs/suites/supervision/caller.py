from kernel_client import services
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import PEER_CLOSED, KernelError
from suites.supervision.protocol import OPERATION_HOLD

WORKER = 0


def main() -> bool:
    startup = Startup()
    try:
        services.call(startup.handles[WORKER], OPERATION_HOLD)
    except KernelError as error:
        return error.code == PEER_CLOSED
    return False
