from kernel_client import capabilities, ipc, processes
from kernel_protocol.identity.rights import RIGHT_SEND
from runtime_selftest.checks import Checks
from suites.scheduling.yielder import TICKS
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.reporting import Context

YIELDER = "suites.scheduling.yielder"
OWN_PRIORITY = 1
YIELDS = 8 * TICKS
PAST_DEADLINE = 0


def run(context: Context, checks: Checks) -> None:
    ticks = ipc.create_endpoint()
    yielder = children.start(
        context.system, YIELDER, priority=OWN_PRIORITY, grants=((ticks, RIGHT_SEND),)
    )
    for _ in range(YIELDS):
        processes.yield_now()
    received = [ipc.receive(ticks, PAST_DEADLINE).message.correlation for _ in range(TICKS)]
    checks.require(
        received == list(range(TICKS)),
        "an equal-priority process runs each time the processor is yielded",
    )
    checks.require(children.finish(yielder) == EXITED_CLEANLY, "the other process finishes")
    capabilities.close(ticks)
