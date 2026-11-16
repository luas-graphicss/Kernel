from kernel_client import system
from kernel_protocol.processes.status import COUNTER_PREEMPTIONS
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, KILLED
from suites.support.reporting import Context

HOLDER = "suites.processes.pattern_holder"
COLLECTOR = "suites.processes.collector"
SEEDS = (0x1111111111111111, 0x2468ACE013579BDF, 0x7FFFFFFFFFFFFFFF, 0x0123456789ABCDEF)
REQUIRED_PREEMPTIONS = 2 * len(SEEDS)


def run(context: Context, checks: Checks) -> None:
    before = system.counters(context.system)
    collector = children.start(context.system, COLLECTOR)
    holders = [children.start(context.system, HOLDER, bytes(str(seed), "ascii")) for seed in SEEDS]
    for holder in holders:
        checks.require(
            children.finish(holder) == EXITED_CLEANLY,
            "integer and floating-point registers survive every switch",
        )
    checks.require(
        children.stop(collector) == KILLED, "the collecting process ran until it was stopped"
    )
    after = system.counters(context.system)
    checks.require(
        after[COUNTER_PREEMPTIONS] - before[COUNTER_PREEMPTIONS] >= REQUIRED_PREEMPTIONS,
        "the processes were switched while they held their patterns",
    )
