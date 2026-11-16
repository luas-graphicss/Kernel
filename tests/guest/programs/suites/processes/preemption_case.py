from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import COUNTER_PREEMPTIONS
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import KILLED
from suites.support.reporting import Context

SPINNER = "suites.processes.spinner"
OWN_PRIORITY = 1
WINDOW_NANOSECONDS = 80000000
DESCHEDULED_NANOSECONDS = 5000000
REQUIRED_RETURNS = 3


def count_returns_to_the_processor() -> int:
    returns = 0
    previous = processes.clock()
    deadline = previous + WINDOW_NANOSECONDS
    while previous < deadline:
        now = processes.clock()
        if now - previous >= DESCHEDULED_NANOSECONDS:
            returns += 1
        previous = now
    return returns


def run(context: Context, checks: Checks) -> None:
    announcements = ipc.create_endpoint()
    before = system.counters(context.system)
    spinner = children.start(
        context.system, SPINNER, priority=OWN_PRIORITY, grants=((announcements, RIGHT_SEND),)
    )
    ipc.receive(announcements)
    checks.require(
        count_returns_to_the_processor() >= REQUIRED_RETURNS,
        "a loop that never yields does not keep the processor",
    )
    after = system.counters(context.system)
    checks.require(
        after[COUNTER_PREEMPTIONS] - before[COUNTER_PREEMPTIONS] >= REQUIRED_RETURNS,
        "the timer preempted the loop",
    )
    checks.require(children.stop(spinner) == KILLED, "an authorized process ends the loop")
    capabilities.close(announcements)
