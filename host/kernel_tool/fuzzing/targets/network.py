import functools

from kernel_services.network.arp.packet import decode_packet
from kernel_services.network.counters import Counters
from kernel_services.network.ethernet.frame import decode_frame
from kernel_services.network.icmp.message import decode_message, decode_quotation
from kernel_services.network.ipv4.header import decode_datagram
from kernel_services.network.limits import (
    NEIGHBORS,
    REASSEMBLY_DATAGRAMS,
    SOCKET_BUFFER_BYTES,
    TCP_CONNECTIONS,
)
from kernel_services.network.stack import Stack
from kernel_services.network.tcp.connection import ESTABLISHED, Connection
from kernel_services.network.tcp.segment import decode_segment
from kernel_services.network.udp.datagram import decode_datagram as decode_user_datagram
from kernel_tool.fuzzing.model import Family, InterpretedTarget, InvariantError
from kernel_tool.fuzzing.targets.stations import (
    GUEST_ADDRESS,
    GUEST_HARDWARE,
    MILLISECOND,
    PEER_ADDRESS,
    PEER_HARDWARE,
    PROPAGATION_NANOSECONDS,
    SECOND,
    Link,
    guest_station,
    peer_station,
)
from kernel_tool.network.malformed import Stations, connection_requests, specimens

ECHO_PORT = 7
PEER_PORT = 40000
BACKLOG = 4
READ_BYTES = 4096
LENGTH_BYTES = 2
MAX_FRAMES = 48
MAX_SEQUENCE_BYTES = 16384
MAX_PACKET_BYTES = 2048
FRAME_INTERVAL_NANOSECONDS = MILLISECOND
QUIET_NANOSECONDS = 300 * SECOND
QUIET_STEPS = 64
DECODERS = 7
SEED_PATIENCE_NANOSECONDS = 5 * SECOND
STREAM = bytes(range(256)) * 16
DIALOGUE_PATIENCE_NANOSECONDS = 120 * SECOND
MAX_DIALOGUE_BYTES = 256
FATES = 8
DROP = 5
DUPLICATE = 6
CORRUPT = 7
BITS_PER_BYTE = 8
DUPLICATE_DELAY_NANOSECONDS = 3 * MILLISECOND
FORGED = Stations(
    guest_hardware=GUEST_HARDWARE,
    guest=GUEST_ADDRESS.to_bytes(4, "big"),
    sender_hardware=PEER_HARDWARE,
    sender=PEER_ADDRESS.to_bytes(4, "big"),
)


class EchoGuest:
    def __init__(self) -> None:
        self.stack = guest_station()
        self._listener = self.stack.tcp.listen(ECHO_PORT, BACKLOG)
        self._port = self.stack.udp.bind(ECHO_PORT)
        self._connections: list[Connection] = []

    def serve(self, now: int) -> None:
        accepted = self._listener.accept()
        while accepted is not None:
            self._connections.append(accepted)
            accepted = self._listener.accept()
        for connection in self._connections:
            received = connection.read(READ_BYTES)
            if received and connection.is_writable():
                connection.write(received, now)
        datagram = self._port.take()
        while datagram is not None:
            source, source_port, data = datagram
            self.stack.udp.send(self._port, source, source_port, data)
            datagram = self._port.take()

    def close(self) -> None:
        self.stack.tcp.abort_all()
        self.stack.udp.unbind_all()


def pack_frames(frames: list[bytes]) -> bytes:
    return b"".join(len(frame).to_bytes(LENGTH_BYTES, "little") + frame for frame in frames)


def unpack_frames(data: bytes) -> list[bytes]:
    frames: list[bytes] = []
    position = 0
    while position + LENGTH_BYTES <= len(data) and len(frames) < MAX_FRAMES:
        length = int.from_bytes(data[position : position + LENGTH_BYTES], "little")
        position += LENGTH_BYTES
        frames.append(data[position : position + length])
        position += length
    return frames


def serve_for_a_while(link: Link, guest: EchoGuest) -> None:
    def keeps_serving() -> bool:
        guest.serve(link.now)
        return False

    link.run_until(keeps_serving, SEED_PATIENCE_NANOSECONDS)


@functools.cache
def recorded_conversation() -> bytes:
    guest = EchoGuest()
    peer = peer_station()
    link = Link(guest.stack, peer)
    peer.send_echo(GUEST_ADDRESS, 1, b"reachable?")
    serve_for_a_while(link, guest)
    port = peer.udp.bind(PEER_PORT)
    peer.udp.send(port, GUEST_ADDRESS, ECHO_PORT, b"a datagram for the echo port")
    serve_for_a_while(link, guest)
    connection = peer.tcp.connect(GUEST_ADDRESS, ECHO_PORT, link.now)
    serve_for_a_while(link, guest)
    connection.write(b"a short stream of bytes", link.now)
    serve_for_a_while(link, guest)
    connection.finish(link.now)
    serve_for_a_while(link, guest)
    return pack_frames(link.delivered_to_guest[:MAX_FRAMES])


def frame_seeds() -> tuple[bytes, ...]:
    malformed = [pack_frames(list(specimen.frames)) for specimen in specimens(FORGED)]
    flood = pack_frames(list(connection_requests(FORGED, ECHO_PORT, BACKLOG * 2)))
    return (recorded_conversation(), flood, *malformed)


def receive_frames(data: bytes) -> None:
    guest = EchoGuest()
    stack = guest.stack
    now = 0
    for frame in unpack_frames(data):
        now += FRAME_INTERVAL_NANOSECONDS
        stack.frame_arrives(frame, now)
        stack.run(now)
        guest.serve(now)
        stack.take_frames()
        check_limits(stack)
    guest.close()
    for _step in range(QUIET_STEPS):
        now += QUIET_NANOSECONDS // QUIET_STEPS
        stack.run(now)
        stack.take_frames()
    if stack.reassembling() != 0:
        raise InvariantError("fragments are still held long after their lifetime")
    if stack.budget.used_bytes != 0:
        raise InvariantError("socket buffers are still charged after every socket was closed")
    if stack.tcp.connection_count() != 0:
        raise InvariantError("connections remain long after every socket was aborted")


def check_limits(stack: Stack) -> None:
    if stack.budget.used_bytes > SOCKET_BUFFER_BYTES:
        raise InvariantError("socket buffers exceed their budget")
    if stack.tcp.connection_count() > TCP_CONNECTIONS:
        raise InvariantError("there are more connections than the limit")
    if stack.reassembling() > REASSEMBLY_DATAGRAMS:
        raise InvariantError("there are more datagrams in reassembly than the limit")
    if stack.interface.neighbors.size() > NEIGHBORS:
        raise InvariantError("there are more neighbors than the limit")


def packet_seeds() -> tuple[bytes, ...]:
    frames = unpack_frames(recorded_conversation())
    return tuple(bytes((decoder,)) + frame for decoder in range(DECODERS) for frame in frames[:4])


def decode_packet_layer(data: bytes) -> None:
    if not data:
        return
    decoder, body = data[0] % DECODERS, data[1:]
    counters = Counters()
    if decoder == 0:
        decode_frame(body)
    elif decoder == 1:
        decode_packet(body)
    elif decoder == 2:
        decode_datagram(body, counters)
    elif decoder == 3:
        decode_message(body)
    elif decoder == 4:
        decode_quotation(body)
    elif decoder == 5:
        decode_user_datagram(body, PEER_ADDRESS, GUEST_ADDRESS, counters)
    else:
        decode_segment(body, PEER_ADDRESS, GUEST_ADDRESS, counters)


def dialogue_seeds() -> tuple[bytes, ...]:
    return (b"", bytes((DROP, 0, 0, 0)), bytes((CORRUPT, 40, DUPLICATE, 0, 0, 0)) * 4)


def converse_over_a_bad_link(data: bytes) -> None:
    plan = iter(data[:MAX_DIALOGUE_BYTES])

    def fate(_sender: int, frame: bytes) -> list[tuple[int, bytes]]:
        choice = next(plan, 0) % FATES
        detail = next(plan, 0)
        if choice == DROP:
            return []
        if choice == DUPLICATE:
            return [
                (PROPAGATION_NANOSECONDS, frame),
                (PROPAGATION_NANOSECONDS + DUPLICATE_DELAY_NANOSECONDS, frame),
            ]
        if choice == CORRUPT and frame:
            damaged = bytearray(frame)
            damaged[detail * len(frame) // 256] ^= 1 << (detail % BITS_PER_BYTE)
            return [(PROPAGATION_NANOSECONDS, bytes(damaged))]
        return [(PROPAGATION_NANOSECONDS, frame)]

    guest = EchoGuest()
    peer = peer_station()
    link = Link(guest.stack, peer, fate)
    connection = peer.tcp.connect(GUEST_ADDRESS, ECHO_PORT, link.now)
    echoed = bytearray()
    sent = 0

    def echoed_everything() -> bool:
        nonlocal sent
        guest.serve(link.now)
        if connection.state == ESTABLISHED and sent < len(STREAM):
            sent += connection.write(STREAM[sent : sent + READ_BYTES], link.now)
        echoed.extend(connection.read(READ_BYTES))
        check_limits(guest.stack)
        return len(echoed) >= len(STREAM)

    link.run_until(echoed_everything, DIALOGUE_PATIENCE_NANOSECONDS)
    if bytes(echoed) != STREAM[: len(echoed)]:
        raise InvariantError("a stream delivered bytes that were not the bytes sent")


TARGETS = (
    InterpretedTarget(
        name="frames",
        family=Family.NETWORK,
        sources=("src/kernel_services/network",),
        max_input_bytes=MAX_SEQUENCE_BYTES,
        seeds=frame_seeds,
        run=receive_frames,
    ),
    InterpretedTarget(
        name="packet-layers",
        family=Family.NETWORK,
        sources=(
            "src/kernel_services/network/ethernet",
            "src/kernel_services/network/arp",
            "src/kernel_services/network/ipv4",
            "src/kernel_services/network/icmp",
            "src/kernel_services/network/udp/datagram.py",
            "src/kernel_services/network/tcp/segment.py",
        ),
        max_input_bytes=MAX_PACKET_BYTES,
        seeds=packet_seeds,
        run=decode_packet_layer,
    ),
    InterpretedTarget(
        name="stream-dialogue",
        family=Family.NETWORK,
        sources=("src/kernel_services/network/tcp",),
        max_input_bytes=MAX_DIALOGUE_BYTES,
        seeds=dialogue_seeds,
        run=converse_over_a_bad_link,
    ),
)
