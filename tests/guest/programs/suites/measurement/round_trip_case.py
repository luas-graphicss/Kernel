from kernel_client import capabilities, ipc, processes
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.wire.message import Message
from kernel_services.echo.protocol import OPERATION_ECHO, OPERATION_STOP
from runtime_selftest.checks import Checks
from suites.measurement.samples import report
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY
from suites.support.reporting import Context

ECHO = "kernel_services.echo.main"
WARM_UP_CALLS = 200
MEASURED_CALLS = 10000
NO_FLAGS = 0
PAYLOAD = b"round trip"


def run(context: Context, checks: Checks) -> None:
    registrations = ipc.create_endpoint()
    service = children.start(context.system, ECHO, grants=((registrations, RIGHT_SEND),))
    endpoint = ipc.receive(registrations).transferred
    request = Message(OPERATION_ECHO, NO_FLAGS, 0, PAYLOAD)
    for _ in range(WARM_UP_CALLS):
        ipc.call(endpoint, request)
    durations = []
    answered = 0
    for _ in range(MEASURED_CALLS):
        started = processes.clock()
        response, _received = ipc.call(endpoint, request)
        durations.append(processes.clock() - started)
        if response.payload == PAYLOAD:
            answered += 1
    ipc.call(endpoint, Message(OPERATION_STOP, NO_FLAGS, 0, b""))
    capabilities.close(endpoint)
    capabilities.close(registrations)
    checks.require(children.finish(service) == EXITED_CLEANLY, "the echo service exits cleanly")
    checks.require(answered == MEASURED_CALLS, "every measured call is answered")
    report("ipc-round-trip", durations)
