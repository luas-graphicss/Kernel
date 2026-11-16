from kernel_client import capabilities, ipc, system
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import COUNTER_FRAMES_FREE
from kernel_protocol.wire.message import Message
from kernel_services.echo.protocol import OPERATION_ECHO, OPERATION_STOP
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.reporting import Context, describe_changes, run_suite

ECHO = "kernel_services.echo.main"
WARM_UP_CYCLES = 100
MEASURED_CYCLES = 10000
NO_FLAGS = 0
PAYLOAD = b"cycle"


def cycle(context: Context, registrations: int, correlation: int) -> bool:
    service = children.start(context.system, ECHO, grants=((registrations, RIGHT_SEND),))
    endpoint = ipc.receive(registrations).transferred
    response, _received = ipc.call(
        endpoint, Message(OPERATION_ECHO, NO_FLAGS, correlation, PAYLOAD)
    )
    ipc.call(endpoint, Message(OPERATION_STOP, NO_FLAGS, correlation, b""))
    capabilities.close(endpoint)
    return (
        children.finish(service) == EXITED_CLEANLY
        and response.payload == PAYLOAD
        and response.correlation == correlation
    )


def run_cycles(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    for correlation in range(WARM_UP_CYCLES):
        checks.require(cycle(context, registrations, correlation), "a warm-up cycle completes")
    warm = system.counters(context.system)
    completed = 0
    for correlation in range(MEASURED_CYCLES):
        if cycle(context, registrations, correlation):
            completed += 1
    after = system.counters(context.system)
    checks.require(completed == MEASURED_CYCLES, "every measured cycle completes")
    checks.require(
        describe_changes(warm, after) == "", "objects, capabilities and endpoints do not grow"
    )
    checks.require(
        after[COUNTER_FRAMES_FREE] == warm[COUNTER_FRAMES_FREE], "free frames do not shrink"
    )
    print(f"cycles: completed={completed} frames-free={after[COUNTER_FRAMES_FREE]}")
    capabilities.close(registrations)


def main() -> bool:
    return run_suite("processes", (("ten-thousand-process-and-ipc-cycles", run_cycles),))
