from kernel_client import capabilities, sockets
from kernel_protocol.errors.codes import INVALID_HANDLE, LIMIT_EXCEEDED
from kernel_protocol.services.network import ACCESS_DATAGRAM
from kernel_services.network.limits import SOCKETS_PER_CLIENT
from runtime_selftest.checks import Checks
from suites.network.platform import NetworkSystem
from suites.support.expectations import error_code
from suites.support.reporting import Context


def run(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    held = []
    for index in range(SOCKETS_PER_CLIENT):
        if index % 2:
            held.append(network.datagram())
        else:
            held.append(network.stream())
    checks.require(
        network.status().sockets == SOCKETS_PER_CLIENT, "a process opens its limit of sockets"
    )
    checks.require(
        error_code(network.stream) == LIMIT_EXCEEDED
        and error_code(network.datagram) == LIMIT_EXCEEDED,
        "one socket beyond the limit of the process is refused",
    )
    held.pop().close()
    replacement = network.stream()
    held.append(replacement)
    checks.require(
        error_code(network.stream) == LIMIT_EXCEEDED, "a closed socket frees exactly one place"
    )
    for socket in held:
        socket.close()
    checks.require(network.status().sockets == 0, "closed sockets leave the service")
    identity, access = network.restrict(ACCESS_DATAGRAM)
    visitor = sockets.Network(system.endpoint(), access)
    abandoned = visitor.datagram()
    visitor.leave()
    checks.require(
        error_code(abandoned.describe) == INVALID_HANDLE
        and error_code(visitor.datagram) == INVALID_HANDLE
        and network.status().sockets == 0,
        "leaving a session closes its sockets and ends it",
    )
    network.revoke(identity)
    capabilities.close(access)
