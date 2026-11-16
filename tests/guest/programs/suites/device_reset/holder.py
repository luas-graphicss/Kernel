from kernel_client import devices, ipc, memory
from kernel_client.processes import Startup
from kernel_protocol.wire.message import Message
from suites.device_reset.requests import submit_read
from suites.support.layout import PAGE_BYTES

OPERATION_SUBMITTED = 1
NO_FLAGS = 0


def submit(device: int) -> None:
    devices.open_session(device, 0)
    submit_read(device, memory.create_buffer(PAGE_BYTES))


def leave_a_request_behind(startup: Startup) -> bool:
    submit(startup.handles[0])
    return True


def wait_for_the_device(startup: Startup) -> bool:
    submit(startup.handles[0])
    ipc.send(startup.handles[1], Message(OPERATION_SUBMITTED, NO_FLAGS, 0, b""))
    devices.wait(startup.handles[0])
    return False


ROLES = {b"leave": leave_a_request_behind, b"linger": wait_for_the_device}


def main() -> bool:
    startup = Startup()
    return ROLES[startup.argument](startup)
