from kernel_client import devices, ipc, memory
from kernel_client.processes import Startup
from kernel_protocol.wire.message import Message
from suites.support.layout import PAGE_BYTES

SAMPLE_BYTES = 16
OPERATION_SUBMITTED = 1
NO_FLAGS = 0


def submit(device: int) -> None:
    buffer = memory.create_buffer(PAGE_BYTES)
    devices.open_session(device, 0)
    devices.submit(device, ((buffer, 0, SAMPLE_BYTES, True),))


def leave_a_request_behind(startup: Startup) -> bool:
    submit(startup.handles[0])
    return True


def linger_with_a_request(startup: Startup) -> bool:
    submit(startup.handles[0])
    ipc.send(startup.handles[1], Message(OPERATION_SUBMITTED, NO_FLAGS, 0, b""))
    ipc.receive(ipc.create_endpoint())
    return False


ROLES = {b"leave": leave_a_request_behind, b"linger": linger_with_a_request}


def main() -> bool:
    startup = Startup()
    return ROLES[startup.argument](startup)
