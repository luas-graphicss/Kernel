import _process
from kernel_client.calls import check, scalar
from kernel_protocol.processes.status import unpack_wait_status
from kernel_protocol.syscalls.numbers import (
    CLOCK_NOW,
    DEADLINE_NEVER,
    PROCESS_INTERRUPT,
    PROCESS_KILL,
    PROCESS_WAIT,
    PROCESS_YIELD,
)
from kernel_protocol.wire.spawn import encode_spawn_request

DEFAULT_PRIORITY = 2


class Startup:
    def __init__(self) -> None:
        self.program, self.argument, self.handles, self.identity = _process.startup()


def clock() -> int:
    return scalar(CLOCK_NOW)


def yield_now() -> None:
    scalar(PROCESS_YIELD)


def spawn(
    system: int,
    program: str,
    argument: bytes = b"",
    priority: int = DEFAULT_PRIORITY,
    heap_bytes: int = 0,
    memory_bytes: int = 0,
    grants: tuple[tuple[int, int], ...] = (),
) -> int:
    request = encode_spawn_request(program, argument, priority, heap_bytes, memory_bytes, grants)
    return check(_process.spawn(system, request))


def wait(handle: int, deadline: int = DEADLINE_NEVER) -> tuple[int, int]:
    return unpack_wait_status(scalar(PROCESS_WAIT, handle, deadline))


def kill(handle: int) -> None:
    scalar(PROCESS_KILL, handle)


def interrupt(handle: int) -> None:
    scalar(PROCESS_INTERRUPT, handle)
