from kernel_client import processes, system
from kernel_protocol.errors.codes import LIMIT_EXCEEDED, OK, KernelError
from kernel_protocol.processes.status import (
    COUNTER_FRAMES_FREE,
    COUNTER_FRAMES_RESERVED,
    COUNTER_PROCESSES,
)
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import KILLED
from suites.support.reporting import Context

SLEEPER = "suites.support.sleeper"
PROFILE_PROCESSES = 16
PROFILE_PROCESS_HEAP_BYTES = 0x400000
START_ATTEMPTS = PROFILE_PROCESSES + 1


def start_until_refused(context: Context) -> tuple[list[int], int]:
    started = []
    for _ in range(START_ATTEMPTS):
        try:
            started.append(
                processes.spawn(context.system, SLEEPER, heap_bytes=PROFILE_PROCESS_HEAP_BYTES)
            )
        except KernelError as error:
            return started, error.code
    return started, OK


def run(context: Context, checks: Checks) -> None:
    before = system.counters(context.system)
    sleepers, refusal = start_until_refused(context)
    full = system.counters(context.system)
    checks.require(
        full[COUNTER_PROCESSES] == PROFILE_PROCESSES,
        "the profile admits sixteen processes at the heap limit",
    )
    checks.require(refusal == LIMIT_EXCEEDED, "the seventeenth process is refused")
    checks.require(
        full[COUNTER_FRAMES_FREE] >= full[COUNTER_FRAMES_RESERVED],
        "sixteen processes leave the supervisor reserve free",
    )
    stopped = [children.stop(sleeper) for sleeper in sleepers]
    checks.require(all(outcome == KILLED for outcome in stopped), "every process is stopped")
    after = system.counters(context.system)
    checks.require(
        after[COUNTER_FRAMES_FREE] == before[COUNTER_FRAMES_FREE],
        "every frame returns after the processes are gone",
    )
