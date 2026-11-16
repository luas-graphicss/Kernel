from runtime_selftest.checks import Checks
from suites.memory.inspector import BUFFER_BYTES
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.reporting import Context

SCRIBBLER = "suites.memory.scribbler"
INSPECTOR = "suites.memory.inspector"
ROUNDS = 2


def run(context: Context, checks: Checks) -> None:
    for _ in range(ROUNDS):
        checks.require(
            children.run(context.system, SCRIBBLER, memory_bytes=BUFFER_BYTES) == EXITED_CLEANLY,
            "a process fills its buffer, heap and stack",
        )
        checks.require(
            children.run(context.system, INSPECTOR, memory_bytes=BUFFER_BYTES) == EXITED_CLEANLY,
            "the next process receives only zeroed memory",
        )
