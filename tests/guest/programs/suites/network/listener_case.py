from kernel_protocol.errors.codes import BAD_STATE, INVALID_ARGUMENT, TIMED_OUT
from kernel_protocol.services.network import MAX_BACKLOG, STATE_LISTENING
from runtime_selftest.checks import Checks
from suites.network.peer import LISTEN_PORT, MILLISECOND, PEER, SECOND
from suites.network.platform import NetworkSystem
from suites.support.expectations import error_code
from suites.support.reporting import Context

CHUNK_BYTES = 4000


def echo_until_end(connection) -> int:
    echoed = 0
    while True:
        data = connection.receive(CHUNK_BYTES, 30 * SECOND)
        if not data:
            return echoed
        connection.send_all(data, 30 * SECOND)
        echoed += len(data)


def run(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    listener = network.stream()
    checks.require(
        error_code(listener.listen, 2) == BAD_STATE, "a socket binds a port before it listens"
    )
    listener.bind(LISTEN_PORT)
    checks.require(
        error_code(listener.listen, 0) == INVALID_ARGUMENT
        and error_code(listener.listen, MAX_BACKLOG + 1) == INVALID_ARGUMENT,
        "a backlog outside the accepted range is refused",
    )
    listener.listen(2)
    checks.require(listener.describe().state == STATE_LISTENING, "the socket listens")
    checks.require(
        error_code(listener.accept, 200 * MILLISECOND) == TIMED_OUT,
        "an accept with no connection ends at its deadline",
    )
    second = network.stream()
    second.bind(LISTEN_PORT)
    checks.require(
        error_code(second.listen, 1) != 0, "a port with a listener takes no second listener"
    )
    second.close()
    print(f"network: listening port={LISTEN_PORT}")
    connection, address, port = listener.accept(30 * SECOND)
    checks.require(address == PEER and port != 0, "the accepted connection names the external peer")
    echoed = echo_until_end(connection)
    connection.finish()
    connection.close()
    listener.close()
    print(f"network: transfer=inbound bytes={echoed}")
    checks.require(echoed > 0, "the inbound connection carried the bytes of the peer")
