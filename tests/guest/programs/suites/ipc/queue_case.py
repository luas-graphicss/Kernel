from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import LIMIT_EXCEEDED, TIMED_OUT, WOULD_DEADLOCK
from kernel_protocol.processes.status import COUNTER_IPC_BYTES
from runtime_selftest.checks import Checks
from suites.ipc.actors import (
    QUEUE_MESSAGES,
    arrives_in_order,
    fill,
    queued_messages,
    start_server,
)
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.reporting import Context

QUOTA_ENDPOINTS = 4
CHARGED_BYTES_PER_MESSAGE = 4096
NO_TRANSFER = 0
PAST_DEADLINE = 0
SHORT_WAIT_NANOSECONDS = 10000000


def check_sender_quota(context: Context, checks: Checks) -> None:
    endpoints = [ipc.create_endpoint() for _ in range(QUOTA_ENDPOINTS + 1)]
    spare = endpoints[QUOTA_ENDPOINTS]
    before = system.counters(context.system)
    fill(endpoints[0], QUEUE_MESSAGES)
    checks.require(
        error_code(ipc.send, endpoints[0], plain(OPERATION_REQUEST)) == WOULD_DEADLOCK,
        "the owner of a full queue is refused instead of blocked",
    )
    for endpoint in endpoints[1:QUOTA_ENDPOINTS]:
        fill(endpoint, QUEUE_MESSAGES)
    queued = QUOTA_ENDPOINTS * QUEUE_MESSAGES
    pending = system.counters(context.system)[COUNTER_IPC_BYTES] - before[COUNTER_IPC_BYTES]
    checks.require(
        queued_messages(context, before) == queued
        and pending == queued * CHARGED_BYTES_PER_MESSAGE,
        "every queued message is charged to its sender",
    )
    checks.require(
        error_code(ipc.send, spare, plain(OPERATION_REQUEST)) == LIMIT_EXCEEDED,
        "a sender is stopped at its pending-bytes quota",
    )
    checks.require(
        arrives_in_order(endpoints[0], QUEUE_MESSAGES), "messages leave in arrival order"
    )
    ipc.send(spare, plain(OPERATION_REQUEST))
    ipc.receive(spare)
    for endpoint in endpoints[1:QUOTA_ENDPOINTS]:
        checks.require(arrives_in_order(endpoint, QUEUE_MESSAGES), "every queue is drained")
    for endpoint in endpoints:
        capabilities.close(endpoint)


def check_blocked_senders(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    drainer, target = start_server(context, b"drain", registrations)
    fill(target, QUEUE_MESSAGES + 1)
    checks.require(
        children.finish(drainer) == EXITED_CLEANLY,
        "a blocked sender resumes when the queue has room and nothing is lost",
    )
    capabilities.close(target)

    idle, target = start_server(context, b"idle", registrations)
    before = system.counters(context.system)
    fill(target, QUEUE_MESSAGES)
    deadline = processes.clock() + SHORT_WAIT_NANOSECONDS
    checks.require(
        error_code(ipc.send, target, plain(OPERATION_REQUEST), NO_TRANSFER, deadline) == TIMED_OUT,
        "a blocked send respects its deadline",
    )
    checks.require(
        error_code(ipc.send, target, plain(OPERATION_REQUEST), NO_TRANSFER, PAST_DEADLINE)
        == TIMED_OUT,
        "a send with a past deadline does not wait",
    )
    checks.require(children.stop(idle) == KILLED, "the receiver is stopped with a full queue")
    checks.require(
        queued_messages(context, before) == 0, "the queue of a dead receiver is released"
    )
    capabilities.close(target)
    capabilities.close(registrations)


def run(context: Context, checks: Checks) -> None:
    check_sender_quota(context, checks)
    check_blocked_senders(context, checks)
