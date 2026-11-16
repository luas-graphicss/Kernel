from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import TIMED_OUT
from runtime_selftest.checks import Checks
from suites.ipc.actors import queued_messages, start_server
from suites.ipc.protocol import OPERATION_PROCEED, OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.reporting import Context

WAIT_NANOSECONDS = 20000000
PAST_DEADLINE = 0
LAST_FINITE_DEADLINE = 0xFFFFFFFFFFFFFFFE
NO_TRANSFER = 0


def call_error(service: int, deadline: int) -> int:
    return error_code(ipc.call, service, plain(OPERATION_REQUEST), NO_TRANSFER, deadline)


def check_receive(checks: Checks) -> None:
    endpoint = ipc.create_endpoint()
    started = processes.clock()
    checks.require(
        error_code(ipc.receive, endpoint, started + WAIT_NANOSECONDS) == TIMED_OUT,
        "a receive on an empty endpoint times out",
    )
    checks.require(
        processes.clock() - started >= WAIT_NANOSECONDS, "the wait lasts until the deadline"
    )
    checks.require(
        error_code(ipc.receive, endpoint, PAST_DEADLINE) == TIMED_OUT,
        "a receive with a past deadline does not wait",
    )
    ipc.send(endpoint, plain(OPERATION_REQUEST))
    checks.require(
        ipc.receive(endpoint, LAST_FINITE_DEADLINE).message.operation == OPERATION_REQUEST,
        "the largest finite deadline is accepted",
    )
    capabilities.close(endpoint)


def check_call_before_dispatch(context: Context, checks: Checks, registrations: int) -> None:
    idle, service = start_server(context, b"idle", registrations)
    before = system.counters(context.system)
    checks.require(
        call_error(service, processes.clock() + WAIT_NANOSECONDS) == TIMED_OUT,
        "a call that is never received times out",
    )
    checks.require(call_error(service, PAST_DEADLINE) == TIMED_OUT, "a past deadline does not wait")
    checks.require(queued_messages(context, before) == 0, "a call that timed out leaves the queue")
    checks.require(children.stop(idle) == KILLED, "the server never saw a request")
    capabilities.close(service)


def check_call_after_dispatch(context: Context, checks: Checks, registrations: int) -> None:
    holder, service = start_server(context, b"holder", registrations)
    checks.require(
        call_error(service, processes.clock() + WAIT_NANOSECONDS) == TIMED_OUT,
        "a call that is received but not answered times out",
    )
    ipc.receive(registrations)
    ipc.send(service, plain(OPERATION_PROCEED))
    checks.require(children.finish(holder) == EXITED_CLEANLY, "a late reply is refused as stale")
    capabilities.close(service)


def run(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    check_receive(checks)
    check_call_before_dispatch(context, checks, registrations)
    check_call_after_dispatch(context, checks, registrations)
    capabilities.close(registrations)
