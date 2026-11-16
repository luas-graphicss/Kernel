from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import TIMED_OUT
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import COUNTER_FRAMES_FREE, COUNTER_MESSAGES
from runtime_selftest.checks import Checks
from suites.processes.litterer import PENDING_MESSAGES
from suites.support import children
from suites.support.expectations import (
    EXITED_CLEANLY,
    KILLED,
    LOAD_PAGE_FAULT,
    error_code,
    faulted,
)
from suites.support.reporting import Context, describe_changes

LITTERER = "suites.processes.litterer"
SETTLE_NANOSECONDS = 20000000
SELF_ENDING = ((b"exit", EXITED_CLEANLY), (b"fault", faulted(LOAD_PAGE_FAULT)))
BLOCKING = (b"receive", b"call")


def unchanged(before: tuple[int, ...], after: tuple[int, ...]) -> bool:
    return (
        describe_changes(before, after) == ""
        and before[COUNTER_FRAMES_FREE] == after[COUNTER_FRAMES_FREE]
    )


def queued_messages(context: Context, before: tuple[int, ...]) -> int:
    return system.counters(context.system)[COUNTER_MESSAGES] - before[COUNTER_MESSAGES]


def run(context: Context, checks: Checks) -> None:
    requests = ipc.create_endpoint()
    grants = ((requests, RIGHT_SEND),)
    before = system.counters(context.system)
    for ending, outcome in SELF_ENDING:
        checks.require(
            children.run(context.system, LITTERER, ending, grants=grants) == outcome,
            "the process ends without releasing what it holds",
        )
        checks.require(
            unchanged(before, system.counters(context.system)),
            "the supervisor releases everything the process held",
        )
    for blocking in BLOCKING:
        litterer = children.start(context.system, LITTERER, blocking, grants=grants)
        checks.require(
            context.wait_for(lambda: queued_messages(context, before) >= PENDING_MESSAGES)
            and context.pause(SETTLE_NANOSECONDS),
            "the process queues its messages and blocks",
        )
        checks.require(children.stop(litterer) == KILLED, "the blocked process is killed")
        checks.require(
            unchanged(before, system.counters(context.system)),
            "a kill releases queued messages, mappings and capabilities",
        )
    checks.require(
        error_code(ipc.receive, requests, processes.clock() + SETTLE_NANOSECONDS) == TIMED_OUT,
        "the request of a killed caller is withdrawn from the queue",
    )
    capabilities.close(requests)
