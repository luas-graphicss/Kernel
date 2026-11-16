from kernel_protocol.errors.codes import (
    BAD_STATE,
    CONNECTION_REFUSED,
    INVALID_ARGUMENT,
    MESSAGE_TOO_LARGE,
    TIMED_OUT,
)
from kernel_protocol.services.network import NO_WAIT
from runtime_selftest.checks import Checks
from suites.network.peer import CLOSED_PORT, ECHO_PORT, MILLISECOND, PEER, SECOND
from suites.network.platform import NetworkSystem
from suites.network.streams import stream_part
from suites.support.expectations import error_code
from suites.support.reporting import Context

LIMIT = 4000
FRAGMENTED_BYTES = 3072
TRUNCATED_LIMIT = 100
TRUNCATED_BYTES = 600
OVERSIZED_BYTES = 4027
BURST = 3


def run(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    socket = network.datagram()
    checks.require(socket.send_to(PEER, ECHO_PORT, b"kernel") == 6, "a datagram is sent")
    address, port, size, data = socket.receive_from(LIMIT, 2 * SECOND)
    checks.require(
        address == PEER and port == ECHO_PORT and size == 6 and data == b"kernel",
        "the echoed datagram names its sender and keeps its boundary",
    )
    checks.require(socket.describe().local_port >= 49152, "the socket took an ephemeral port")
    socket.send_to(PEER, ECHO_PORT, b"")
    address, port, size, data = socket.receive_from(LIMIT, 2 * SECOND)
    checks.require(size == 0 and data == b"", "an empty datagram arrives as an empty datagram")
    large = stream_part(11, 0, FRAGMENTED_BYTES // 256)
    socket.send_to(PEER, ECHO_PORT, large)
    address, port, size, data = socket.receive_from(LIMIT, 4 * SECOND)
    checks.require(
        size == FRAGMENTED_BYTES and data == large,
        "a datagram larger than the link is fragmented and reassembled both ways",
    )
    socket.send_to(PEER, ECHO_PORT, large[:TRUNCATED_BYTES])
    address, port, size, data = socket.receive_from(TRUNCATED_LIMIT, 2 * SECOND)
    checks.require(
        size == TRUNCATED_BYTES and data == large[:TRUNCATED_LIMIT],
        "a datagram longer than the receive limit reports its true size",
    )
    for index in range(BURST):
        socket.send_to(PEER, ECHO_PORT, bytes((index,)) * 8)
    seen = []
    for _ in range(BURST):
        seen.append(socket.receive_from(LIMIT, 2 * SECOND)[3])
    checks.require(
        sorted(seen) == [bytes((index,)) * 8 for index in range(BURST)],
        "every datagram of a burst arrives whole whatever the order",
    )
    checks.require(
        error_code(socket.send_to, PEER, ECHO_PORT, bytes(OVERSIZED_BYTES)) == MESSAGE_TOO_LARGE
        and error_code(socket.send_to, PEER, 0, b"x") == INVALID_ARGUMENT
        and error_code(socket.send_to, 0, ECHO_PORT, b"x") == INVALID_ARGUMENT,
        "an oversized datagram or one to no station and port is refused",
    )
    checks.require(
        error_code(socket.receive_from, LIMIT, 200 * MILLISECOND) == TIMED_OUT
        and error_code(socket.receive_from, LIMIT, NO_WAIT) == TIMED_OUT,
        "a receive with nothing queued ends at its deadline",
    )
    socket.send_to(PEER, CLOSED_PORT, b"nobody listens")
    checks.require(
        error_code(socket.receive_from, LIMIT, 2 * SECOND) == CONNECTION_REFUSED,
        "a datagram to a port without listener is reported by the next receive",
    )
    checks.require(error_code(socket.bind, 5000) == BAD_STATE, "a bound socket binds no other port")
    socket.close()
    bound = network.datagram()
    checks.require(bound.bind(5000) == 5000, "a datagram socket binds the port it asks for")
    other = network.datagram()
    checks.require(error_code(other.bind, 5000) != 0, "a port in use is refused to a second socket")
    other.close()
    bound.close()
