from kernel_protocol.errors.codes import (
    BAD_STATE,
    CONNECTION_REFUSED,
    INVALID_ARGUMENT,
    TIMED_OUT,
    UNREACHABLE,
)
from kernel_protocol.services.network import (
    STATE_CONNECTED,
    STATE_FINISHED,
    STATE_NEW,
)
from runtime_selftest.checks import Checks
from suites.network.peer import (
    ABSENT,
    CLOSED_PORT,
    ECHO_PORT,
    MILLISECOND,
    PEER,
    REMOTE,
    SECOND,
    SINK_PORT,
)
from suites.network.platform import NetworkSystem
from suites.network.streams import (
    receive_digest,
    receive_exactly,
    send_stream,
    stream_part,
)
from suites.support.expectations import error_code
from suites.support.reporting import Context

ECHOED_BLOCKS = 20
UPLOAD_SEED = 3
UPLOAD_BYTES = 20480


def run(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    stream = network.stream()
    checks.require(stream.describe().state == STATE_NEW, "a new socket has no connection")
    checks.require(
        error_code(stream.send, b"x") == BAD_STATE and error_code(stream.receive, 1) == BAD_STATE,
        "a socket without a connection neither sends nor receives",
    )
    stream.connect(PEER, ECHO_PORT, 5 * SECOND)
    description = stream.describe()
    checks.require(
        description.state == STATE_CONNECTED
        and description.remote_address == PEER
        and description.remote_port == ECHO_PORT
        and description.local_port >= 49152,
        "a connection to the external stack is established and described",
    )
    checks.require(
        error_code(stream.connect, PEER, ECHO_PORT, SECOND) == BAD_STATE,
        "a connected socket connects no second time",
    )
    message = stream_part(7, 0, ECHOED_BLOCKS)
    stream.send_all(message, 5 * SECOND)
    checks.require(
        receive_exactly(stream, len(message)) == message,
        "the bytes sent come back in order from the echo service",
    )
    checks.require(
        error_code(stream.receive, 100, 200 * MILLISECOND) == TIMED_OUT,
        "a receive on an idle connection ends at its deadline",
    )
    stream.send_all(b"again", SECOND)
    checks.require(
        receive_exactly(stream, 5) == b"again", "the connection is intact after the deadline"
    )
    stream.finish()
    checks.require(
        stream.receive(100, 5 * SECOND) == b"", "the peer closes after the local side finished"
    )
    checks.require(
        error_code(stream.send, b"x", SECOND) == BAD_STATE
        and stream.describe().state >= STATE_FINISHED,
        "a finished socket sends nothing more",
    )
    stream.close()
    refused = network.stream()
    checks.require(
        error_code(refused.connect, PEER, CLOSED_PORT, 5 * SECOND) == CONNECTION_REFUSED,
        "a port without listener refuses the connection",
    )
    refused.close()
    lost = network.stream()
    checks.require(
        error_code(lost.connect, ABSENT, ECHO_PORT, 10 * SECOND) == UNREACHABLE,
        "a station that never resolves fails the connection",
    )
    lost.close()
    slow = network.stream()
    checks.require(
        error_code(slow.connect, REMOTE, ECHO_PORT, 500 * MILLISECOND) == TIMED_OUT,
        "a connection that gets no answer ends at its deadline",
    )
    checks.require(
        error_code(slow.connect, 0, ECHO_PORT, SECOND) == INVALID_ARGUMENT,
        "a connection names a station and a port",
    )
    slow.close()
    upload = network.stream()
    upload.connect(PEER, SINK_PORT, 5 * SECOND)
    send_stream(upload, UPLOAD_SEED, UPLOAD_BYTES)
    upload.finish()
    digest = receive_digest(upload)
    checks.require(
        upload.receive(1, 5 * SECOND) == b"", "the half-closed connection ends after the digest"
    )
    upload.close()
    print(f"network: transfer=upload bytes={UPLOAD_BYTES} sha256={digest}")
    checks.require(network.status().connections <= 1, "closed connections leave the service")
