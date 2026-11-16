from kernel_client import capabilities, ipc, processes, system
from kernel_protocol.errors.codes import TIMED_OUT
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.processes.status import COUNTER_PREEMPTIONS
from runtime_selftest.checks import Checks
from suites.scheduling.protocol import OPERATION_NOTE, OPERATION_REQUEST, OPERATION_STOP, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, KILLED, error_code
from suites.support.reporting import Context

WORKER = "suites.scheduling.worker"
HOG = "suites.processes.spinner"
SERVER_PRIORITY = 3
HOG_PRIORITY = 2
DONATED_PREEMPTIONS = 2
UNDONATED_WAIT_NANOSECONDS = 30000000


def run(context: Context, checks: Checks) -> None:
    reports = ipc.create_endpoint()
    grants = ((reports, RIGHT_SEND),)
    worker = children.start(context.system, WORKER, priority=SERVER_PRIORITY, grants=grants)
    service = ipc.receive(reports).transferred
    hog = children.start(context.system, HOG, priority=HOG_PRIORITY, grants=grants)
    ipc.receive(reports)

    before = system.counters(context.system)
    ipc.call(service, plain(OPERATION_REQUEST))
    after = system.counters(context.system)
    checks.require(
        after[COUNTER_PREEMPTIONS] - before[COUNTER_PREEMPTIONS] <= DONATED_PREEMPTIONS,
        "a server runs at the priority of the caller that waits for it",
    )
    deadline = processes.clock() + UNDONATED_WAIT_NANOSECONDS
    checks.require(
        error_code(ipc.receive, reports, deadline) == TIMED_OUT,
        "the donation ends with the reply",
    )
    checks.require(children.stop(hog) == KILLED, "the process that held the processor is stopped")
    checks.require(
        ipc.receive(reports).message.operation == OPERATION_NOTE,
        "the server finishes its own work at its own priority",
    )
    ipc.send(service, plain(OPERATION_STOP))
    checks.require(children.finish(worker) == EXITED_CLEANLY, "the server stops on request")
    capabilities.close(service)
    capabilities.close(reports)
