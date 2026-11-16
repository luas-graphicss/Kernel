from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import INVALID_ARGUMENT, LIMIT_EXCEEDED
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import (
    COUNTER_FRAMES_FREE,
    COUNTER_FRAMES_RESERVED,
    COUNTER_FRAMES_USABLE,
)
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.children import CHILD_HEAP_BYTES
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.layout import PAGE_BYTES
from suites.support.reporting import Context

HOARDER = "suites.memory.hoarder"
SLEEPER = "suites.support.sleeper"
MIB = 1 << 20
LOCAL_QUOTA_BYTES = MIB
LOCAL_BLOCKS = b"262144 4"
GLOBAL_QUOTA_BYTES = 192 * MIB
GLOBAL_BLOCKS = b"4194304 48"
HEAP_LIMIT_BYTES = 4 * MIB
PRIORITY = processes.DEFAULT_PRIORITY


def spawn_error(context: Context, heap_bytes: int, memory_bytes: int) -> int:
    return error_code(
        processes.spawn, context.system, SLEEPER, b"", PRIORITY, heap_bytes, memory_bytes, ()
    )


def check_saturation(context: Context, checks: Checks) -> None:
    before = system.counters(context.system)
    reports = ipc.create_endpoint()
    hoarder = children.start(
        context.system,
        HOARDER,
        GLOBAL_BLOCKS,
        memory_bytes=GLOBAL_QUOTA_BYTES,
        grants=((reports, RIGHT_SEND),),
    )
    ipc.receive(reports)
    saturated = system.counters(context.system)
    checks.require(
        saturated[COUNTER_FRAMES_USABLE] - saturated[COUNTER_FRAMES_FREE]
        >= GLOBAL_QUOTA_BYTES // PAGE_BYTES,
        "the admitted process really holds its memory",
    )
    checks.require(
        saturated[COUNTER_FRAMES_FREE] >= saturated[COUNTER_FRAMES_RESERVED],
        "the supervisor reserve stays free under saturation",
    )
    checks.require(
        spawn_error(context, CHILD_HEAP_BYTES, GLOBAL_QUOTA_BYTES) == LIMIT_EXCEEDED,
        "a process that would overcommit memory is not admitted",
    )
    checks.require(
        children.stop(children.start(context.system, SLEEPER)) == KILLED,
        "a small process still starts under saturation",
    )
    checks.require(children.stop(hoarder) == KILLED, "the saturating process is stopped")
    capabilities.close(reports)
    after = system.counters(context.system)
    checks.require(
        after[COUNTER_FRAMES_FREE] == before[COUNTER_FRAMES_FREE],
        "every frame returns when the process is gone",
    )


def run(context: Context, checks: Checks) -> None:
    checks.require(
        children.run(context.system, HOARDER, LOCAL_BLOCKS, memory_bytes=LOCAL_QUOTA_BYTES)
        == EXITED_CLEANLY,
        "a process is refused memory exactly at its quota",
    )
    checks.require(
        spawn_error(context, HEAP_LIMIT_BYTES + PAGE_BYTES, 0) == LIMIT_EXCEEDED,
        "a heap above the profile limit is refused",
    )
    checks.require(
        spawn_error(context, CHILD_HEAP_BYTES + 1, 0) == INVALID_ARGUMENT,
        "a heap that is not a whole number of pages is refused",
    )
    check_saturation(context, checks)
