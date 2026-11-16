from kernel_client import capabilities, ipc, processes, services
from kernel_protocol.errors.codes import BAD_STATE, TIMED_OUT, KernelError
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import WAIT_REASON_EXIT
from kernel_protocol.services.lifecycle import OPERATION_REGISTER, OPERATION_STOP, encode_supervisor
from kernel_services.init.manifest import Service

POLL = 0
START_SLICE_NANOSECONDS = 50000000
START_TIMEOUT_NANOSECONDS = 20000000000
STOP_TIMEOUT_NANOSECONDS = 20000000000
NO_ENDPOINT = 0


class Running:
    def __init__(self, service: Service, process: int) -> None:
        self.service = service
        self.process = process
        self.endpoint = NO_ENDPOINT
        self.identity = 0
        self.announcement = b""


def has_exited(process: int) -> bool:
    try:
        processes.wait(process, POLL)
    except KernelError as error:
        if error.code != TIMED_OUT:
            raise
        return False
    return True


def terminate(process: int) -> None:
    try:
        processes.kill(process)
    except KernelError as error:
        if error.code != BAD_STATE:
            raise


def await_announcement(registration: int, process: int) -> ipc.Received | None:
    deadline = processes.clock() + START_TIMEOUT_NANOSECONDS
    while processes.clock() < deadline:
        try:
            announced = ipc.receive(registration, processes.clock() + START_SLICE_NANOSECONDS)
        except KernelError as error:
            if error.code != TIMED_OUT:
                raise
            if has_exited(process):
                return None
            continue
        if announced.message.operation == OPERATION_REGISTER and announced.transferred != 0:
            return announced
        services.discard_transfer(announced)
    return None


def start(
    system: int,
    registration: int,
    supervisor: int,
    service: Service,
    grants: tuple[tuple[int, int], ...],
    role: bytes = b"",
) -> Running:
    granted = [(registration, RIGHT_SEND)]
    granted.extend(grants)
    process = processes.spawn(
        system,
        service.program,
        encode_supervisor(supervisor, role),
        service.priority,
        service.heap_bytes,
        0,
        tuple(granted),
    )
    running = Running(service, process)
    announced = await_announcement(registration, process)
    if announced is not None:
        running.endpoint = announced.transferred
        running.identity = announced.sender
        running.announcement = announced.message.payload
    return running


def is_alive(running: Running) -> bool:
    return running.endpoint != NO_ENDPOINT and not has_exited(running.process)


def ask_to_stop(running: Running) -> None:
    try:
        deadline = processes.clock() + STOP_TIMEOUT_NANOSECONDS
        services.call(running.endpoint, OPERATION_STOP, deadline=deadline)
    except KernelError:
        terminate(running.process)


def stop(running: Running) -> bool:
    if running.endpoint == NO_ENDPOINT:
        terminate(running.process)
    else:
        ask_to_stop(running)
        capabilities.close(running.endpoint)
        running.endpoint = NO_ENDPOINT
    reason, value = processes.wait(running.process)
    capabilities.close(running.process)
    return reason == WAIT_REASON_EXIT and value == 0
