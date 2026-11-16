from kernel_client import capabilities, ipc, services, sockets
from kernel_protocol.errors.codes import ACCESS_DENIED, INVALID_ARGUMENT, INVALID_HANDLE, NOT_FOUND
from kernel_protocol.identity.rights import RIGHT_SEND
from kernel_protocol.services.network import (
    ACCESS_ALL,
    ACCESS_CONNECT,
    ACCESS_ECHO,
    KIND_STREAM,
    OPERATION_DESCRIBE,
    OPERATION_ENTER,
    OPERATION_OPEN,
    encode_request,
    encode_word,
)
from runtime_selftest.checks import Checks
from suites.network.peer import ECHO_PORT, PEER, SECOND
from suites.network.platform import NetworkSystem
from suites.support import children
from suites.support.expectations import EXITED_CLEANLY, error_code
from suites.support.reporting import Context

INTRUDER = "suites.network.intruder"
LIMITED = ACCESS_CONNECT | ACCESS_ECHO
UNKNOWN_RIGHT = 0x40


def run(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    endpoint = system.endpoint()
    checks.require(network.rights == ACCESS_ALL, "the supervisor holds every right of the service")
    checks.require(
        error_code(network.restrict, 0) == INVALID_ARGUMENT
        and error_code(network.restrict, UNKNOWN_RIGHT) == INVALID_ARGUMENT,
        "a restriction to no right or to unknown rights is refused",
    )
    identity, access = network.restrict(LIMITED)
    limited = sockets.Network(endpoint, access)
    checks.require(limited.rights == LIMITED, "a restricted access grants exactly its rights")
    checks.require(limited.echo(PEER, 2 * SECOND) > 0, "a granted operation is served")
    checks.require(
        error_code(limited.datagram) == ACCESS_DENIED
        and error_code(limited.status) == ACCESS_DENIED
        and error_code(limited.neighbors) == ACCESS_DENIED
        and error_code(limited.restrict, ACCESS_ECHO) == ACCESS_DENIED,
        "datagrams, inspection and delegation are denied without their rights",
    )
    stream = limited.stream()
    stream.bind(8090)
    checks.require(
        error_code(stream.listen, 1) == ACCESS_DENIED, "listening is denied without its right"
    )
    stream.close()
    connected = limited.stream()
    connected.connect(PEER, ECHO_PORT, 5 * SECOND)
    stale = encode_request(network.instance + 1, connected.handle, b"")
    checks.require(
        error_code(services.call, endpoint, OPERATION_DESCRIBE, stale) == INVALID_HANDLE,
        "a handle of another instance of the service is refused",
    )
    network.revoke(identity)
    checks.require(
        error_code(limited.echo, PEER, SECOND) == INVALID_HANDLE
        and error_code(connected.describe) == INVALID_HANDLE,
        "revoking an access ends the sessions and sockets opened through it",
    )
    checks.require(
        error_code(sockets.Network, endpoint, access) == ACCESS_DENIED,
        "a revoked access admits no new session",
    )
    checks.require(error_code(network.revoke, identity) == NOT_FOUND, "an access is revoked once")
    capabilities.close(access)
    forged = ipc.create_endpoint()
    checks.require(
        error_code(sockets.Network, endpoint, forged) == ACCESS_DENIED,
        "an endpoint the service did not issue grants nothing",
    )
    capabilities.close(forged)
    checks.require(
        children.run(context.system, INTRUDER, grants=((endpoint, RIGHT_SEND),)) == EXITED_CLEANLY,
        "a process without a network capability opens no socket and reaches no device",
    )
    checks.require(
        error_code(services.call, endpoint, OPERATION_ENTER) == ACCESS_DENIED
        and error_code(
            services.call,
            endpoint,
            OPERATION_OPEN,
            encode_request(network.instance, 999, encode_word(KIND_STREAM)),
        )
        == INVALID_HANDLE,
        "entering without presenting an access and forged sessions are refused",
    )
