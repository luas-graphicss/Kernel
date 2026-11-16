from kernel_client import capabilities, ipc
from runtime_selftest.checks import Checks
from suites.scheduling.tickers import count_turns
from suites.support.reporting import Context

URGENT = 2
BACKGROUND = 3
WINDOW_NANOSECONDS = 400000000


def run(context: Context, checks: Checks) -> None:
    reports = ipc.create_endpoint()
    turns = count_turns(context, reports, (URGENT, BACKGROUND), WINDOW_NANOSECONDS)
    checks.require(len(turns) == 2, "both tickers report")
    urgent, background = turns
    checks.require(urgent > background, "the more urgent process gets most of the processor")
    checks.require(background > 0, "aging keeps the less urgent process from starving")
    capabilities.close(reports)
