from kernel_client import capabilities, ipc, system
from kernel_protocol.errors.codes import ACCESS_DENIED, PEER_CLOSED
from kernel_protocol.identity.rights import RIGHT_RECEIVE, RIGHT_SEND
from runtime_selftest.checks import Checks
from suites.ipc.actors import queued_messages, start_server
from suites.ipc.protocol import OPERATION_REQUEST, plain
from suites.support import children
from suites.support.expectations import KILLED, error_code
from suites.support.reporting import Context

QUEUED_BEFORE_CLOSE = 3


def run(context: Context, checks: Checks) -> None:
    endpoint = ipc.create_endpoint()
    sender = capabilities.derive(endpoint, RIGHT_SEND)
    checks.require(
        error_code(capabilities.derive, endpoint, RIGHT_RECEIVE) == ACCESS_DENIED,
        "the receive right cannot be derived",
    )
    checks.require(
        error_code(ipc.receive, sender) == ACCESS_DENIED, "receive needs the receive right"
    )
    before = system.counters(context.system)
    for correlation in range(QUEUED_BEFORE_CLOSE):
        ipc.send(sender, plain(OPERATION_REQUEST, correlation))
    capabilities.close(endpoint)
    checks.require(
        queued_messages(context, before) == 0, "closing the receiving capability drops the queue"
    )
    checks.require(
        error_code(ipc.send, sender, plain(OPERATION_REQUEST)) == PEER_CLOSED,
        "an endpoint without a receiver refuses messages",
    )
    capabilities.close(sender)

    registrations = ipc.create_endpoint()
    idle, service = start_server(context, b"idle", registrations)
    checks.require(
        error_code(ipc.receive, service) == ACCESS_DENIED,
        "only the owner receives from its endpoint",
    )
    checks.require(children.stop(idle) == KILLED, "the owner is stopped")
    capabilities.close(service)
    capabilities.close(registrations)
