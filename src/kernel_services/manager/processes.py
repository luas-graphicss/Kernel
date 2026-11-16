from kernel_client import capabilities, ipc, processes, services
from kernel_protocol.errors.codes import BAD_STATE, TIMED_OUT, WOULD_DEADLOCK, KernelError
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import REASON_NAMES, WAIT_REASON_EXIT
from kernel_protocol.services.lifecycle import OPERATION_REGISTER, OPERATION_STOP

POLL = 0
SLICE_NANOSECONDS = 20000000
NO_ENDPOINT = 0
NO_MEMORY_LIMIT = 0
EXIT_SUCCEEDED = 0
STILL_RUNNING_CODES = (TIMED_OUT, WOULD_DEADLOCK)
NOT_ANNOUNCED = "the program did not announce itself in time"


class Program:
    def __init__(self, module: str, priority: int, heap_bytes: int, is_server: bool) -> None:
        self.module = module
        self.priority = priority
        self.heap_bytes = heap_bytes
        self.is_server = is_server


class Started:
    def __init__(self, process: int) -> None:
        self.process = process
        self.endpoint = NO_ENDPOINT
        self.identity = 0
        self.announcement = b""


def has_exited(process: int) -> bool:
    try:
        processes.wait(process, POLL)
    except KernelError as error:
        if error.code not in STILL_RUNNING_CODES:
            raise
        return False
    return True


def terminate(process: int) -> None:
    try:
        processes.kill(process)
    except KernelError as error:
        if error.code != BAD_STATE:
            raise


def reap(process: int) -> tuple[int, int]:
    reason, value = processes.wait(process)
    capabilities.close(process)
    return reason, value


def describe(reason: int, value: int) -> str:
    return f"reason={REASON_NAMES[reason]} value={value}"


def release(started: Started) -> None:
    if started.endpoint != NO_ENDPOINT:
        capabilities.close(started.endpoint)
        started.endpoint = NO_ENDPOINT


def collect(started: Started) -> tuple[int, int]:
    release(started)
    return reap(started.process)


def stop(started: Started, is_server: bool, timeout_nanoseconds: int) -> bool:
    if is_server and started.endpoint != NO_ENDPOINT:
        try:
            deadline = processes.clock() + timeout_nanoseconds
            services.call(started.endpoint, OPERATION_STOP, deadline=deadline)
        except KernelError:
            terminate(started.process)
    else:
        terminate(started.process)
    reason, value = collect(started)
    if not is_server:
        return True
    return reason == WAIT_REASON_EXIT and value == EXIT_SUCCEEDED


class Launcher:
    def __init__(self, system: int, identity: int) -> None:
        self.system = system
        self.identity = identity

    def launch(
        self,
        program: Program,
        grants: tuple[tuple[int, int], ...],
        argument: bytes,
        timeout_nanoseconds: int,
    ) -> Started:
        registration = ipc.create_endpoint()
        try:
            return self._launch(program, registration, grants, argument, timeout_nanoseconds)
        finally:
            capabilities.close(registration)

    def _launch(
        self,
        program: Program,
        registration: int,
        grants: tuple[tuple[int, int], ...],
        argument: bytes,
        timeout_nanoseconds: int,
    ) -> Started:
        granted = [(registration, RIGHT_SEND)]
        granted.extend(grants)
        process = processes.spawn(
            self.system,
            program.module,
            argument,
            program.priority,
            program.heap_bytes,
            NO_MEMORY_LIMIT,
            tuple(granted),
        )
        started = Started(process)
        announced = self._await(registration, process, timeout_nanoseconds)
        if announced is None:
            terminate(process)
            reap(process)
            raise KernelError(TIMED_OUT, NOT_ANNOUNCED)
        started.identity = announced.sender
        started.announcement = announced.message.payload
        started.endpoint = announced.transferred
        if program.is_server and started.endpoint == NO_ENDPOINT:
            terminate(process)
            reap(process)
            raise KernelError(TIMED_OUT, NOT_ANNOUNCED)
        return started

    def _await(
        self, registration: int, process: int, timeout_nanoseconds: int
    ) -> ipc.Received | None:
        deadline = processes.clock() + timeout_nanoseconds
        while processes.clock() < deadline:
            try:
                announced = ipc.receive(registration, processes.clock() + SLICE_NANOSECONDS)
            except KernelError as error:
                if error.code != TIMED_OUT:
                    raise
                if has_exited(process):
                    return None
                continue
            if announced.message.operation == OPERATION_REGISTER:
                return announced
            services.discard_transfer(announced)
        return None
