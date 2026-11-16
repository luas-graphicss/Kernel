from kernel_client import services
from kernel_client.processes import clock
from kernel_protocol.errors.codes import TIMED_OUT, KernelError
from kernel_protocol.services.network import (
    NO_WAIT,
    OPERATION_ACCEPT,
    WAIT_FOREVER,
    encode_request,
    encode_wait,
)
from kernel_services.network.limits import SOCKET_BUFFER_BYTES
from runtime_selftest.checks import Checks
from suites.network.peer import MILLISECOND, PEER, SECOND, SILENT_PORT
from suites.network.platform import NetworkSystem
from suites.support.expectations import error_code
from suites.support.reporting import Context

WAITING_PORT = 8081
CHUNK = bytes(2048)
MAX_ACCEPTED_BYTES = 0x800000


def abandoned_accept(system: NetworkSystem, network, listener) -> int:
    request = encode_request(network.instance, listener.handle, encode_wait(WAIT_FOREVER))
    deadline = clock() + 200 * MILLISECOND
    return error_code(services.call, system.endpoint(), OPERATION_ACCEPT, request, 0, deadline)


def fill(stream) -> int:
    accepted = 0
    while accepted < MAX_ACCEPTED_BYTES:
        try:
            accepted += stream.send(CHUNK, 300 * MILLISECOND)
        except KernelError:
            return accepted
    return accepted


def run(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    listener = network.stream()
    listener.bind(WAITING_PORT)
    listener.listen(1)
    checks.require(
        abandoned_accept(system, network, listener) == TIMED_OUT,
        "a caller that stops waiting leaves its request behind",
    )
    checks.require(
        error_code(listener.accept, NO_WAIT) == TIMED_OUT,
        "a new request replaces the abandoned one and polls without blocking",
    )
    checks.require(
        abandoned_accept(system, network, listener) == TIMED_OUT,
        "the socket still waits after a cancelled request",
    )
    listener.close()
    checks.require(network.status().sockets == 0, "closing the socket cancels what waited on it")
    silent = network.stream()
    silent.connect(PEER, SILENT_PORT, 5 * SECOND)
    accepted = fill(silent)
    checks.require(
        accepted > 0 and accepted < MAX_ACCEPTED_BYTES,
        "a peer that never reads stops the sender instead of growing its buffers",
    )
    checks.require(
        error_code(silent.send, CHUNK, 200 * MILLISECOND) == TIMED_OUT,
        "a send with no room ends at its deadline",
    )
    held = network.status().buffered_bytes
    checks.require(
        held > 0 and held <= SOCKET_BUFFER_BYTES, "the bytes held stay inside the buffer budget"
    )
    silent.close()
    checks.require(
        context.wait_for(lambda: network.status().buffered_bytes == 0),
        "closing the socket returns its buffers",
    )
