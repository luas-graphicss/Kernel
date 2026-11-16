from kernel_client import capabilities, processes
from kernel_protocol.errors.codes import ACCESS_DENIED, BAD_STATE, INVALID_HANDLE, TIMED_OUT
from kernel_protocol.identity.rights import RIGHT_ADMIN, RIGHT_READ
from runtime_selftest.checks import Checks
from suites.support import children
from suites.support.expectations import (
    EXITED_CLEANLY,
    EXITED_FAILING,
    KILLED,
    LOAD_PAGE_FAULT,
    error_code,
    faulted,
)
from suites.support.reporting import Context

EXITING = "suites.processes.exiting"
SLEEPER = "suites.support.sleeper"
SHORT_WAIT_NANOSECONDS = 5000000
PAST_DEADLINE = 0


def check_exit_status(context: Context, checks: Checks) -> None:
    checks.require(
        children.run(context.system, EXITING, b"succeed") == EXITED_CLEANLY,
        "a program that succeeds exits with status zero",
    )
    checks.require(
        children.run(context.system, EXITING, b"fail") == EXITED_FAILING,
        "a program that fails exits with status one",
    )
    checks.require(
        children.run(context.system, EXITING, b"fault") == faulted(LOAD_PAGE_FAULT),
        "a fault is reported with its cause",
    )


def run(context: Context, checks: Checks) -> None:
    check_exit_status(context, checks)
    sleeper = children.start(context.system, SLEEPER)
    checks.require(
        error_code(processes.wait, sleeper, processes.clock() + SHORT_WAIT_NANOSECONDS)
        == TIMED_OUT,
        "waiting for a live process respects the deadline",
    )
    checks.require(
        error_code(processes.wait, sleeper, PAST_DEADLINE) == TIMED_OUT,
        "a deadline in the past expires at once",
    )
    reader = capabilities.derive(sleeper, RIGHT_READ)
    administrator = capabilities.derive(sleeper, RIGHT_ADMIN)
    checks.require(
        error_code(processes.kill, reader) == ACCESS_DENIED, "kill needs the admin right"
    )
    checks.require(
        error_code(processes.interrupt, reader) == ACCESS_DENIED,
        "interrupt needs the admin right",
    )
    checks.require(
        error_code(processes.wait, administrator) == ACCESS_DENIED, "wait needs the read right"
    )
    processes.kill(administrator)
    checks.require(
        error_code(processes.kill, sleeper) == BAD_STATE, "a process is not killed twice"
    )
    checks.require(processes.wait(reader) == KILLED, "wait reports the kill")
    checks.require(processes.wait(sleeper) == KILLED, "the exit status stays readable")
    for handle in (reader, administrator, sleeper):
        capabilities.close(handle)
    checks.require(
        error_code(capabilities.close, sleeper) == INVALID_HANDLE,
        "a process handle is not closed twice",
    )
    checks.require(
        error_code(processes.wait, sleeper) == INVALID_HANDLE,
        "a closed process handle names nothing",
    )
