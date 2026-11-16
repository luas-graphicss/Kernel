from kernel_protocol.errors.codes import TIMED_OUT, KernelError
from kernel_services.network.counters import NAMES, TCP_OUT_OF_ORDER, TCP_RETRANSMITTED
from runtime_selftest.checks import Checks
from suites.network.listener_case import echo_until_end
from suites.network.peer import (
    ECHO_PORT,
    LISTEN_PORT,
    PEER,
    SECOND,
    SINK_PORT,
    SLOW_PORT,
    SOURCE_PORT,
)
from suites.network.platform import NetworkSystem, run_with_network
from suites.network.streams import (
    RECEIVE_BYTES,
    TRANSFER_TIMEOUT,
    encode_source_request,
    format_checksum,
    receive_checksum,
    receive_digest,
    send_stream,
    stream_part,
)
from suites.support.reporting import Context

UPLOAD_SEED = 17
UPLOAD_BYTES = 131072
DOWNLOAD_SEED = 23
DOWNLOAD_BYTES = 131072
RELAY_SEED = 29
RELAY_BYTES = 65536
SLOW_SEED = 31
SLOW_BYTES = 32768
DATAGRAM_BLOCKS = 12
DATAGRAM_ATTEMPTS = 24
DATAGRAM_ROUNDS = 4
LIMIT = 4000


def upload(system: NetworkSystem, context: Context, checks: Checks) -> None:
    stream = system.network().stream()
    stream.connect(PEER, SINK_PORT, 30 * SECOND)
    send_stream(stream, UPLOAD_SEED, UPLOAD_BYTES)
    stream.finish()
    digest = receive_digest(stream)
    stream.close()
    checks.require(len(digest) == 64, "the peer answered with the digest of what it received")
    print(f"network: transfer=upload bytes={UPLOAD_BYTES} sha256={digest}")


def download(system: NetworkSystem, context: Context, checks: Checks) -> None:
    stream = system.network().stream()
    stream.connect(PEER, SOURCE_PORT, 30 * SECOND)
    stream.send_all(encode_source_request(DOWNLOAD_SEED, DOWNLOAD_BYTES), TRANSFER_TIMEOUT)
    received, checksum = receive_checksum(stream)
    stream.close()
    checks.require(received == DOWNLOAD_BYTES, "the peer sent every byte that was asked for")
    print(f"network: transfer=download bytes={received} crc32={format_checksum(checksum)}")


def relay(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    source = network.stream()
    sink = network.stream()
    source.connect(PEER, SOURCE_PORT, 30 * SECOND)
    sink.connect(PEER, SINK_PORT, 30 * SECOND)
    source.send_all(encode_source_request(RELAY_SEED, RELAY_BYTES), TRANSFER_TIMEOUT)
    relayed = 0
    while True:
        part = source.receive(RECEIVE_BYTES, TRANSFER_TIMEOUT)
        if not part:
            break
        sink.send_all(part, TRANSFER_TIMEOUT)
        relayed += len(part)
    source.close()
    sink.finish()
    digest = receive_digest(sink)
    sink.close()
    checks.require(relayed == RELAY_BYTES, "every byte received from the peer was sent back")
    print(f"network: transfer=relay bytes={relayed} sha256={digest}")


def inbound(system: NetworkSystem, context: Context, checks: Checks) -> None:
    listener = system.network().stream()
    listener.bind(LISTEN_PORT)
    listener.listen(2)
    print(f"network: listening port={LISTEN_PORT}")
    connection, address, _port = listener.accept(60 * SECOND)
    echoed = echo_until_end(connection)
    connection.finish()
    connection.close()
    listener.close()
    checks.require(address == PEER and echoed > 0, "the external peer connected and was echoed")
    print(f"network: transfer=inbound bytes={echoed}")


def exchange(socket, payload: bytes) -> bool:
    for _ in range(DATAGRAM_ATTEMPTS):
        socket.send_to(PEER, ECHO_PORT, payload)
        try:
            while True:
                if socket.receive_from(LIMIT, SECOND)[3] == payload:
                    return True
        except KernelError as error:
            if error.code != TIMED_OUT:
                raise
    return False


def fragments(system: NetworkSystem, context: Context, checks: Checks) -> None:
    socket = system.network().datagram()
    delivered = 0
    for index in range(DATAGRAM_ROUNDS):
        if exchange(socket, stream_part(40 + index, 0, DATAGRAM_BLOCKS)):
            delivered += 1
    socket.close()
    checks.require(
        delivered == DATAGRAM_ROUNDS,
        "fragmented datagrams cross the link whole in both directions",
    )
    print(f"network: transfer=datagrams delivered={delivered} bytes={DATAGRAM_BLOCKS * 256}")


def slow_reader(system: NetworkSystem, context: Context, checks: Checks) -> None:
    stream = system.network().stream()
    stream.connect(PEER, SLOW_PORT, 30 * SECOND)
    send_stream(stream, SLOW_SEED, SLOW_BYTES)
    stream.finish()
    digest = receive_digest(stream)
    stream.close()
    checks.require(len(digest) == 64, "a peer that reads slowly still receives every byte")
    print(f"network: transfer=slow-reader bytes={SLOW_BYTES} sha256={digest}")


def summary(system: NetworkSystem, context: Context, checks: Checks) -> None:
    network = system.network()
    status = network.status()
    retransmitted = status.counters[NAMES.index(TCP_RETRANSMITTED)]
    reordered = status.counters[NAMES.index(TCP_OUT_OF_ORDER)]
    checks.require(
        status.buffered_bytes == 0
        or context.wait_for(lambda: network.status().buffered_bytes == 0),
        "the transfers left no buffer behind",
    )
    print(f"network: recovery retransmitted={retransmitted} out-of-order={reordered}")


CASES = (
    ("upload-verified-by-the-peer", upload),
    ("download-verified-by-checksum", download),
    ("relay-through-the-guest", relay),
    ("inbound-connection", inbound),
    ("fragmented-datagrams", fragments),
    ("slow-reader", slow_reader),
    ("buffers-returned", summary),
)


def main() -> bool:
    return run_with_network("network-interop", CASES)
