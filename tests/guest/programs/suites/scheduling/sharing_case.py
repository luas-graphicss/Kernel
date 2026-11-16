from kernel_client import capabilities, ipc
from runtime_selftest.checks import Checks
from suites.scheduling.tickers import count_turns
from suites.support.reporting import Context

PRIORITY = 2
EQUALS = (PRIORITY, PRIORITY, PRIORITY)
WINDOW_NANOSECONDS = 150000000
FAIRNESS_FACTOR = 3


def run(context: Context, checks: Checks) -> None:
    reports = ipc.create_endpoint()
    alone = count_turns(context, reports, (PRIORITY,), WINDOW_NANOSECONDS)
    together = sorted(count_turns(context, reports, EQUALS, WINDOW_NANOSECONDS))
    checks.require(len(alone) == 1 and len(together) == len(EQUALS), "every ticker reports")
    fewest, most = together[0], together[-1]
    checks.require(fewest > 0, "every process of the same priority gets the processor")
    checks.require(
        most * FAIRNESS_FACTOR <= alone[0] * (FAIRNESS_FACTOR - 1),
        "no process keeps the processor as if it ran alone",
    )
    checks.require(fewest * FAIRNESS_FACTOR >= most, "the processor is shared evenly")
    capabilities.close(reports)
