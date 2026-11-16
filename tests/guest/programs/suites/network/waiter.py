from kernel_client import services, sockets
from kernel_client.processes import Startup
from kernel_protocol.errors.codes import PEER_CLOSED, KernelError
from suites.network.peer import ECHO_PORT, PEER, SECOND

SERVICE = 0
ACCESS = 1
CONNECTED = 2
OPERATION_CONNECTED = 16


def main() -> bool:
    startup = Startup()
    network = sockets.Network(startup.handles[SERVICE], startup.handles[ACCESS])
    stream = network.stream()
    stream.connect(PEER, ECHO_PORT, 5 * SECOND)
    services.note(startup.handles[CONNECTED], OPERATION_CONNECTED)
    try:
        stream.receive(1)
    except KernelError as error:
        return error.code == PEER_CLOSED
    return False
