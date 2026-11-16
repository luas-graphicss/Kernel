from kernel_client import ipc, processes, system
from kernel_protocol.errors.codes import TIMED_OUT, KernelError, error_name
from kernel_protocol.processes.status import (
    COUNTER_BUFFERS,
    COUNTER_CAPABILITIES,
    COUNTER_ENDPOINTS,
    COUNTER_IPC_BYTES,
    COUNTER_MESSAGES,
    COUNTER_OBJECTS,
    COUNTER_PROCESSES,
)
from runtime_selftest.checks import CheckError, Checks
from suites.support.expectations import error_code

TRACKED_COUNTERS = (
    ("processes", COUNTER_PROCESSES),
    ("objects", COUNTER_OBJECTS),
    ("capabilities", COUNTER_CAPABILITIES),
    ("endpoints", COUNTER_ENDPOINTS),
    ("messages", COUNTER_MESSAGES),
    ("ipc-bytes", COUNTER_IPC_BYTES),
    ("buffers", COUNTER_BUFFERS),
)


POLL_NANOSECONDS = 2000000
PATIENCE_NANOSECONDS = 5000000000


class Context:
    def __init__(self, system_handle: int, identity: int) -> None:
        self.system = system_handle
        self.identity = identity
        self._silent = ipc.create_endpoint()

    def pause(self, nanoseconds: int) -> bool:
        deadline = processes.clock() + nanoseconds
        return error_code(ipc.receive, self._silent, deadline) == TIMED_OUT

    def wait_for(self, condition) -> bool:
        deadline = processes.clock() + PATIENCE_NANOSECONDS
        while not condition():
            if processes.clock() >= deadline:
                return False
            self.pause(POLL_NANOSECONDS)
        return True


def describe_changes(before: tuple[int, ...], after: tuple[int, ...]) -> str:
    changes = ""
    for name, index in TRACKED_COUNTERS:
        if before[index] != after[index]:
            changes += f" {name}={before[index]}->{after[index]}"
    return changes


def run_case(suite: str, name: str, run, context: Context) -> bool:
    checks = Checks()
    before = system.counters(context.system)
    try:
        run(context, checks)
    except CheckError as error:
        print(f'test: suite={suite} case={name} result=failed check="{error.args[0]}"')
        return False
    except KernelError as error:
        print(f"test: suite={suite} case={name} result=failed error={error_name(error.code)}")
        return False
    changes = describe_changes(before, system.counters(context.system))
    if changes:
        print(f"test: suite={suite} case={name} result=leaked{changes}")
        return False
    print(f"test: suite={suite} case={name} checks={checks.passed} result=ok")
    return True


def run_suite(suite: str, cases) -> bool:
    startup = processes.Startup()
    context = Context(startup.handles[0], startup.identity)
    succeeded = True
    for name, run in cases:
        succeeded = run_case(suite, name, run, context) and succeeded
    return succeeded
