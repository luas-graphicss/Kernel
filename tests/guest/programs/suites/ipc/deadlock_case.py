from kernel_client import capabilities, ipc
from kernel_protocol.errors.codes import WOULD_DEADLOCK
from runtime_selftest.checks import Checks
from suites.ipc.actors import start_server
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.raw import read_word
from suites.support.reporting import Context


def run(context: Context, checks: Checks) -> None:
    endpoint = ipc.create_endpoint()
    checks.require(
        error_code(ipc.call, endpoint, plain(OPERATION_REQUEST)) == WOULD_DEADLOCK,
        "a process cannot call its own endpoint",
    )
    callback, service = start_server(context, b"callback", endpoint)
    response, _received = ipc.call(service, plain(OPERATION_REQUEST), endpoint)
    checks.require(
        read_word(response.payload, 0) == WOULD_DEADLOCK,
        "a call back into the waiting caller is refused",
    )
    checks.require(children.finish(callback) == EXITED_CLEANLY, "the server keeps running")
    capabilities.close(service)
    capabilities.close(endpoint)
