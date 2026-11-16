from kernel_client import capabilities, ipc, processes
from kernel_protocol.errors.codes import OK, PEER_CLOSED, TIMED_OUT
from kernel_protocol.identity.rights import RIGHT_SEND
from runtime_selftest.checks import Checks
from suites.scheduling.protocol import OPERATION_REQUEST, OPERATION_STOP, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.raw import word
from suites.support.reporting import Context

RACER = "suites.scheduling.racer"
DEADLINE_NANOSECONDS = 5000000
REPLY_OFFSETS_NANOSECONDS = (-2000000, -500000, -100000, -10000, 0, 10000, 100000, 500000, 2000000)
NO_TRANSFER = 0
ANSWERED = (OK, OK)
EXPIRED = (TIMED_OUT, PEER_CLOSED)


def race(service: int, reports: int, offset: int) -> tuple[int, int]:
    deadline = processes.clock() + DEADLINE_NANOSECONDS
    request = plain(OPERATION_REQUEST, 0, word(deadline + offset))
    caller_code = error_code(ipc.call, service, request, NO_TRANSFER, deadline)
    return caller_code, ipc.receive(reports).message.correlation


def run(context: Context, checks: Checks) -> None:
    reports = ipc.create_endpoint()
    racer = children.start(context.system, RACER, grants=((reports, RIGHT_SEND),))
    service = ipc.receive(reports).transferred
    outcomes = [race(service, reports, offset) for offset in REPLY_OFFSETS_NANOSECONDS]
    checks.require(
        all(outcome in (ANSWERED, EXPIRED) for outcome in outcomes),
        "caller and server always agree on whether the reply was delivered",
    )
    checks.require(outcomes[0] == ANSWERED, "a reply well before the deadline is delivered")
    checks.require(outcomes[-1] == EXPIRED, "a reply well after the deadline is refused")
    ipc.send(service, plain(OPERATION_STOP))
    checks.require(children.finish(racer) == EXITED_CLEANLY, "the server stops on request")
    capabilities.close(service)
    capabilities.close(reports)
