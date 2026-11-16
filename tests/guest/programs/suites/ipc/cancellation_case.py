from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import BAD_STATE, CANCELLED, OK
from runtime_selftest.checks import Checks
from suites.ipc.actors import QUEUE_MESSAGES, fill, queued_messages, start_caller, start_server
from suites.ipc.protocol import OPERATION_PROCEED, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.reporting import Context

BUSY_PROGRAM = "suites.processes.collector"


def interrupt_when_blocked(context: Context, child: int) -> bool:
    attempts = []

    def interrupted() -> bool:
        attempts.append(error_code(processes.interrupt, child))
        return attempts[-1] != BAD_STATE

    return context.wait_for(interrupted) and attempts[-1] == OK


def check_before_dispatch(context: Context, checks: Checks, registrations: int) -> None:
    idle, service = start_server(context, b"idle", registrations)
    before = system.counters(context.system)
    caller = start_caller(context, "call", CANCELLED, service)
    checks.require(
        context.wait_for(lambda: queued_messages(context, before) == 1), "the call is queued"
    )
    processes.interrupt(caller)
    checks.require(children.finish(caller) == EXITED_CLEANLY, "the caller sees the cancellation")
    checks.require(
        queued_messages(context, before) == 0, "a cancelled call is withdrawn before dispatch"
    )
    checks.require(children.stop(idle) == KILLED, "the server never saw the request")
    capabilities.close(service)


def check_after_dispatch(context: Context, checks: Checks, registrations: int) -> None:
    holder, service = start_server(context, b"holder", registrations)
    caller = start_caller(context, "call", CANCELLED, service)
    ipc.receive(registrations)
    processes.interrupt(caller)
    checks.require(
        children.finish(caller) == EXITED_CLEANLY, "a dispatched call can still be cancelled"
    )
    ipc.send(service, plain(OPERATION_PROCEED))
    checks.require(
        children.finish(holder) == EXITED_CLEANLY, "a reply to a cancelled call finds no caller"
    )
    capabilities.close(service)


def check_other_waits(context: Context, checks: Checks, registrations: int) -> None:
    receiver = start_caller(context, "receive", CANCELLED)
    checks.require(interrupt_when_blocked(context, receiver), "a blocked receive is interrupted")
    checks.require(children.finish(receiver) == EXITED_CLEANLY, "the receiver sees it")

    idle, service = start_server(context, b"idle", registrations)
    fill(service, QUEUE_MESSAGES)
    sender = start_caller(context, "send", CANCELLED, service)
    checks.require(interrupt_when_blocked(context, sender), "a blocked send is interrupted")
    checks.require(children.finish(sender) == EXITED_CLEANLY, "the sender sees it")
    checks.require(children.stop(idle) == KILLED, "the receiver is stopped")
    capabilities.close(service)

    busy = children.start(context.system, BUSY_PROGRAM)
    checks.require(
        error_code(processes.interrupt, busy) == BAD_STATE,
        "a process that is not waiting cannot be interrupted",
    )
    checks.require(children.stop(busy) == KILLED, "the busy process is stopped")


def run(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    check_before_dispatch(context, checks, registrations)
    check_after_dispatch(context, checks, registrations)
    check_other_waits(context, checks, registrations)
    capabilities.close(registrations)
