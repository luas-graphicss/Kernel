from kernel_client import ipc, system
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import COUNTER_MESSAGES
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.reporting import Context

SERVER = "suites.ipc.server"
CALLER = "suites.ipc.caller"
QUEUE_MESSAGES = 64
NO_TARGET = 0


def start_server(context: Context, role: bytes, registrations: int) -> tuple[int, int]:
    server = children.start(context.system, SERVER, role, grants=((registrations, RIGHT_SEND),))
    return server, ipc.receive(registrations).transferred


def start_caller(context: Context, mode: str, expected: int, target: int = NO_TARGET) -> int:
    grants = ((target, RIGHT_SEND),) if target != NO_TARGET else ()
    argument = bytes(f"{mode} {expected}", "ascii")
    return children.start(context.system, CALLER, argument, grants=grants)


def queued_messages(context: Context, before: tuple[int, ...]) -> int:
    return system.counters(context.system)[COUNTER_MESSAGES] - before[COUNTER_MESSAGES]


def fill(endpoint: int, count: int) -> None:
    for correlation in range(count):
        ipc.send(endpoint, plain(OPERATION_REQUEST, correlation))


def arrives_in_order(endpoint: int, count: int) -> bool:
    return all(ipc.receive(endpoint).message.correlation == expected for expected in range(count))
