from kernel_client import capabilities, ipc, system
from kernel_protocol.errors.codes import PEER_CLOSED
from runtime_selftest.checks import Checks
from suites.ipc.actors import QUEUE_MESSAGES, fill, queued_messages, start_caller, start_server
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.reporting import Context

SETTLE_NANOSECONDS = 20000000


def check_death_after_dispatch(context: Context, checks: Checks, registrations: int) -> None:
    leaver, service = start_server(context, b"leaver", registrations)
    checks.require(
        error_code(ipc.call, service, plain(OPERATION_REQUEST)) == PEER_CLOSED,
        "a call ends when the server exits without replying",
    )
    checks.require(children.finish(leaver) == EXITED_CLEANLY, "the server left on its own")
    checks.require(
        error_code(ipc.send, service, plain(OPERATION_REQUEST)) == PEER_CLOSED,
        "an endpoint without an owner refuses messages",
    )
    capabilities.close(service)


def check_death_before_dispatch(context: Context, checks: Checks, registrations: int) -> None:
    idle, service = start_server(context, b"idle", registrations)
    before = system.counters(context.system)
    caller = start_caller(context, "call", PEER_CLOSED, service)
    checks.require(
        context.wait_for(lambda: queued_messages(context, before) == 1), "the call is queued"
    )
    checks.require(children.stop(idle) == KILLED, "the server dies with the call queued")
    checks.require(
        children.finish(caller) == EXITED_CLEANLY, "a queued call ends when the server dies"
    )
    capabilities.close(service)


def check_death_with_blocked_sender(context: Context, checks: Checks, registrations: int) -> None:
    idle, service = start_server(context, b"idle", registrations)
    fill(service, QUEUE_MESSAGES)
    sender = start_caller(context, "send", PEER_CLOSED, service)
    checks.require(context.pause(SETTLE_NANOSECONDS), "the sender waits for room in the queue")
    checks.require(children.stop(idle) == KILLED, "the receiver dies with a sender waiting")
    checks.require(
        children.finish(sender) == EXITED_CLEANLY, "a waiting sender is told the peer is gone"
    )
    capabilities.close(service)


def run(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    check_death_after_dispatch(context, checks, registrations)
    check_death_before_dispatch(context, checks, registrations)
    check_death_with_blocked_sender(context, checks, registrations)
    capabilities.close(registrations)
