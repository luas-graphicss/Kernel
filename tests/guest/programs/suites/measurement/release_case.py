from kernel_client import processes, system
from kernel_protocol.processes.status import COUNTER_FRAMES_FREE
from runtime_selftest.checks import Checks
from suites.measurement.samples import report
from suites.support import children
from suites.support.expectations import KILLED
from suites.support.reporting import Context

HOLDER = "suites.measurement.holder"
ROUNDS = 50
SETTLE_NANOSECONDS = 20000000


def frames_free(context: Context) -> int:
    return system.counters(context.system)[COUNTER_FRAMES_FREE]


def frames_restored(context: Context, baseline: int):
    def restored() -> bool:
        return frames_free(context) == baseline

    return restored


def run(context: Context, checks: Checks) -> None:
    durations = []
    released = 0
    for _ in range(ROUNDS):
        baseline = frames_free(context)
        child = children.start(context.system, HOLDER)
        context.pause(SETTLE_NANOSECONDS)
        started = processes.clock()
        killed = children.stop(child) == KILLED
        if context.wait_for(frames_restored(context, baseline)) and killed:
            released += 1
        durations.append(processes.clock() - started)
    checks.require(released == ROUNDS, "every killed process returns its frames")
    report("release-after-exit", durations)
