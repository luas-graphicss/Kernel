from kernel_client import capabilities, ipc, processes
from kernel_protocol.errors.codes import TIMED_OUT
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

EXITING = "suites.processes.exiting"
CLOCK_READS = 2000
SIGNED_LIMIT = 1 << 63
FAR_DEADLINES = (0xFFFFFFFFFFFFFFFE, SIGNED_LIMIT, SIGNED_LIMIT - 1, 1 << 62)
PAST_DEADLINES = (0, 1)
PROMPT_NANOSECONDS = 1000000000


def clock_is_monotonic() -> bool:
    previous = processes.clock()
    for _ in range(CLOCK_READS):
        now = processes.clock()
        if now < previous:
            return False
        previous = now
    return 0 < previous < SIGNED_LIMIT


def run(context: Context, checks: Checks) -> None:
    checks.require(clock_is_monotonic(), "the clock never goes back and fits the result")
    for deadline in FAR_DEADLINES:
        child = children.start(context.system, EXITING, b"succeed")
        checks.require(
            processes.wait(child, deadline) == EXITED_CLEANLY,
            "a deadline near the numeric limit behaves as the far future",
        )
        capabilities.close(child)
    endpoint = ipc.create_endpoint()
    for deadline in PAST_DEADLINES:
        checks.require(
            error_code(ipc.receive, endpoint, deadline) == TIMED_OUT,
            "a deadline before the current time expires at once",
        )
    started = processes.clock()
    checks.require(
        error_code(ipc.receive, endpoint, started + 1) == TIMED_OUT
        and processes.clock() - started < PROMPT_NANOSECONDS,
        "a deadline one nanosecond ahead expires promptly",
    )
    capabilities.close(endpoint)
