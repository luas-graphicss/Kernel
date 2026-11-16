import pytest

from doubles.links import ABSENT, GUEST, PEER, pair, until
from doubles.wire import MILLISECOND, MTU, SECOND, Wire, station
from kernel_protocol.errors.codes import (
    CONNECTION_REFUSED,
    LIMIT_EXCEEDED,
    OK,
    UNREACHABLE,
)
from kernel_services.network.arp.cache import NeighborCache
from kernel_services.network.arp.packet import (
    OPERATION_REPLY,
    OPERATION_REQUEST,
    ArpPacket,
    decode_packet,
    encode_packet,
)
from kernel_services.network.counters import (
    ARP_MALFORMED,
    ARP_QUEUE_REFUSED,
    ARP_REQUESTS_ANSWERED,
    ARP_UNRESOLVED,
    DATAGRAMS_REASSEMBLED,
    FRAMES_FOREIGN,
    FRAMES_UNSUPPORTED,
    ICMP_ECHO_ANSWERED,
    ICMP_LIMITED,
    ICMP_UNSUPPORTED,
    IPV4_BAD_SOURCE,
    IPV4_FOREIGN,
    IPV4_PROTOCOL,
    UDP_DELIVERED,
    UDP_NO_LISTENER,
    UDP_QUEUE_FULL,
)
from kernel_services.network.ethernet.frame import (
    BROADCAST,
    ETHERTYPE_ARP,
    ETHERTYPE_IPV4,
    HEADER_BYTES,
    MINIMUM_PAYLOAD_BYTES,
    decode_frame,
    encode_frame,
)
from kernel_services.network.icmp import echo as echoes
from kernel_services.network.icmp.limiter import RateLimiter
from kernel_services.network.icmp.message import (
    MAXIMUM_ECHO_BYTES,
    TYPE_ECHO_REQUEST,
    encode_echo,
)
from kernel_services.network.ipv4.address import format_address, is_host, parse_address
from kernel_services.network.ipv4.fragmentation import split
from kernel_services.network.ipv4.header import PROTOCOL_ICMP, encode_datagram
from kernel_services.network.limits import (
    ICMP_BURST,
    NEIGHBOR_LIFETIME_NANOSECONDS,
    RESOLUTION_ATTEMPTS,
    RESOLUTION_DATAGRAMS,
    RESOLUTION_RETRY_NANOSECONDS,
    RESOLUTION_TARGETS,
    UDP_QUEUE_DATAGRAMS,
)
from kernel_services.network.stack import Stack

MINUTE = 60 * SECOND
STRANGER = parse_address("10.0.2.77")
STRANGER_HARDWARE = bytes((0x02, 0, 0, 0, 0, 0x77))
UNKNOWN_PROTOCOL = 99


def frame_for(
    stack: Stack, source: int, protocol: int, payload: bytes, destination: int = 0
) -> bytes:
    target = destination or stack.interface.route.address
    datagram = encode_datagram(source, target, protocol, 9, 0, payload)
    return encode_frame(stack.interface.hardware, STRANGER_HARDWARE, ETHERTYPE_IPV4, datagram)


def resolution(stack: Stack, packet: ArpPacket, source: bytes = STRANGER_HARDWARE) -> bytes:
    return encode_frame(BROADCAST, source, ETHERTYPE_ARP, encode_packet(packet))


def carries_a_datagram(frame: bytes) -> bool:
    decoded = decode_frame(frame)
    return decoded is not None and decoded.ethertype == ETHERTYPE_IPV4


def echo(wire: Wire, stack: Stack, destination: str, identity: int = 1, size: int = 32):
    request = stack.echoes.start(parse_address(destination), identity, bytes(size), wire.now)
    assert stack.send_echo(request.destination, identity, request.data) == OK
    wire.settle()
    return request


def test_short_frames_are_padded_and_decoded_frames_name_their_stations() -> None:
    frame = encode_frame(BROADCAST, STRANGER_HARDWARE, ETHERTYPE_ARP, b"abc")
    decoded = decode_frame(frame)

    assert len(frame) == HEADER_BYTES + MINIMUM_PAYLOAD_BYTES
    assert decoded is not None
    assert (decoded.destination, decoded.source, decoded.ethertype) == (
        BROADCAST,
        STRANGER_HARDWARE,
        ETHERTYPE_ARP,
    )
    assert decode_frame(frame[:13]) is None
    assert decode_frame(BROADCAST + BROADCAST + frame[12:]) is None
    assert decode_frame(frame + bytes(1500)) is None


def test_addresses_are_parsed_strictly_and_formatted_back() -> None:
    assert format_address(parse_address("10.0.2.15")) == "10.0.2.15"
    assert not is_host(parse_address("0.0.0.0"))
    assert not is_host(parse_address("224.0.0.1"))
    assert not is_host(parse_address("127.0.0.1"))
    assert not is_host(parse_address("255.255.255.255"))
    for malformed in ("10.0.2", "10.0.2.256", "10.0.2.015", "10.0.2.x", "10..2.1", ""):
        with pytest.raises(Exception, match="four decimal octets"):
            parse_address(malformed)


def test_a_resolution_packet_survives_its_encoding_and_odd_ones_are_refused() -> None:
    packet = ArpPacket(
        OPERATION_REQUEST, STRANGER_HARDWARE, STRANGER, bytes(6), parse_address(GUEST)
    )
    encoded = encode_packet(packet)
    decoded = decode_packet(encoded)

    assert decoded is not None
    assert decoded.sender_address == STRANGER and decoded.target_address == parse_address(GUEST)
    assert decode_packet(encoded[:27]) is None
    assert decode_packet(b"\x00\x06" + encoded[2:]) is None
    assert decode_packet(encoded[:7] + b"\x09" + encoded[8:]) is None
    assert decode_packet(encoded[:8] + BROADCAST + encoded[14:]) is None


def test_two_stations_resolve_each_other_and_answer_an_echo() -> None:
    wire, left, right = pair()

    request = echo(wire, left, PEER)

    assert until(wire, lambda: request.status == OK, MINUTE)
    assert request.round_trip_nanoseconds > 0
    assert left.interface.neighbors.entries() == [(parse_address(PEER), right.interface.hardware)]
    assert right.counters.value(ARP_REQUESTS_ANSWERED) == 1
    assert right.counters.value(ICMP_ECHO_ANSWERED) == 1


def test_a_station_that_never_answers_is_reported_unreachable_after_bounded_attempts() -> None:
    wire, left, _right = pair()

    request = echo(wire, left, ABSENT)

    assert until(wire, lambda: request.status != echoes.PENDING, MINUTE)
    assert request.status == UNREACHABLE
    assert wire.now == RESOLUTION_ATTEMPTS * RESOLUTION_RETRY_NANOSECONDS
    assert left.counters.value(ARP_UNRESOLVED) == 1
    requests = [frame for sender, frame in wire.carried if sender == 0]
    assert len(requests) == RESOLUTION_ATTEMPTS
    assert left.interface.neighbors.size() == 0


def test_pending_resolutions_hold_a_bounded_number_of_stations_and_datagrams() -> None:
    wire, left, _right = pair()
    for host in range(RESOLUTION_TARGETS):
        assert left.send_echo(parse_address(f"10.0.2.{100 + host}"), host, b"x") == OK
    for _ in range(RESOLUTION_DATAGRAMS - 1):
        assert left.send_echo(parse_address("10.0.2.100"), 0, b"x") == OK

    assert left.send_echo(parse_address("10.0.2.100"), 0, b"x") == LIMIT_EXCEEDED
    assert left.send_echo(parse_address("10.0.2.200"), 0, b"x") == LIMIT_EXCEEDED
    assert left.counters.value(ARP_QUEUE_REFUSED) == 2
    wire.settle()
    assert until(wire, lambda: left.counters.value(ARP_UNRESOLVED) == RESOLUTION_TARGETS, MINUTE)


def test_a_full_neighbor_table_forgets_the_entry_closest_to_expiry() -> None:
    cache = NeighborCache(2, NEIGHBOR_LIFETIME_NANOSECONDS)
    cache.learn(1, b"\x02\x00\x00\x00\x00\x01", 0)
    cache.learn(2, b"\x02\x00\x00\x00\x00\x02", 10)

    cache.learn(3, b"\x02\x00\x00\x00\x00\x03", 20)

    assert [address for address, _hardware in cache.entries()] == [2, 3]
    assert cache.lookup(2, NEIGHBOR_LIFETIME_NANOSECONDS + 10) is None
    assert cache.lookup(3, NEIGHBOR_LIFETIME_NANOSECONDS + 10) is not None
    cache.expire(NEIGHBOR_LIFETIME_NANOSECONDS + 20)
    assert cache.size() == 0


def test_resolution_packets_that_lie_about_their_sender_teach_nothing() -> None:
    wire, left, _right = pair()
    guest = parse_address(GUEST)
    claims_receiver = ArpPacket(OPERATION_REPLY, STRANGER_HARDWARE, guest, bytes(6), guest)
    off_link = ArpPacket(
        OPERATION_REQUEST, STRANGER_HARDWARE, parse_address("192.0.2.1"), bytes(6), guest
    )
    forged = ArpPacket(OPERATION_REQUEST, b"\x02\x00\x00\x00\x00\x55", STRANGER, bytes(6), guest)
    unsolicited = ArpPacket(
        OPERATION_REPLY, STRANGER_HARDWARE, STRANGER, bytes(6), parse_address(PEER)
    )

    for packet in (claims_receiver, off_link, forged):
        wire.inject(0, resolution(left, packet))
    wire.inject(0, resolution(left, unsolicited))

    assert left.counters.value(ARP_MALFORMED) == 3
    assert left.interface.neighbors.size() == 0


def test_frames_and_datagrams_meant_for_others_are_counted_and_dropped() -> None:
    wire, left, right = pair()
    request = encode_echo(TYPE_ECHO_REQUEST, 1, 1, b"data")
    to_other_hardware = encode_frame(
        b"\x02\x00\x00\x00\x00\x99", STRANGER_HARDWARE, ETHERTYPE_IPV4, b"x"
    )
    unknown_ethertype = encode_frame(left.interface.hardware, STRANGER_HARDWARE, 0x86DD, b"x")
    to_other_station = frame_for(left, STRANGER, PROTOCOL_ICMP, request, parse_address(PEER))
    from_itself = frame_for(left, parse_address(GUEST), PROTOCOL_ICMP, request)
    unknown_protocol = frame_for(left, STRANGER, UNKNOWN_PROTOCOL, b"payload!")

    for frame in (
        to_other_hardware,
        unknown_ethertype,
        to_other_station,
        from_itself,
        unknown_protocol,
    ):
        wire.inject(0, frame)

    assert left.counters.value(FRAMES_FOREIGN) == 1
    assert left.counters.value(FRAMES_UNSUPPORTED) == 1
    assert left.counters.value(IPV4_FOREIGN) == 1
    assert left.counters.value(IPV4_BAD_SOURCE) == 1
    assert left.counters.value(IPV4_PROTOCOL) == 1
    assert right.counters.value(ICMP_ECHO_ANSWERED) == 0


def test_echo_answers_are_rate_limited_per_burst() -> None:
    wire, left, _right = pair()
    request = encode_echo(TYPE_ECHO_REQUEST, 1, 1, b"data")

    for _ in range(ICMP_BURST + 5):
        wire.inject(0, frame_for(left, STRANGER, PROTOCOL_ICMP, request))

    assert left.counters.value(ICMP_ECHO_ANSWERED) == ICMP_BURST
    assert left.counters.value(ICMP_LIMITED) == 5


def test_an_echo_request_larger_than_the_limit_is_not_answered() -> None:
    wire, left, _right = pair()
    request = encode_echo(TYPE_ECHO_REQUEST, 1, 2, bytes(MAXIMUM_ECHO_BYTES + 8))
    guest = left.interface.route.address

    for fragmentation, piece in split(request, MTU):
        datagram = encode_datagram(STRANGER, guest, PROTOCOL_ICMP, 5, fragmentation, piece)
        wire.inject(
            0, encode_frame(left.interface.hardware, STRANGER_HARDWARE, ETHERTYPE_IPV4, datagram)
        )

    assert left.counters.value(DATAGRAMS_REASSEMBLED) == 1
    assert left.counters.value(ICMP_UNSUPPORTED) == 1
    assert left.counters.value(ICMP_ECHO_ANSWERED) == 0


def test_a_rate_limiter_refills_one_token_per_interval_up_to_its_burst() -> None:
    limiter = RateLimiter(2, 100 * MILLISECOND)

    assert [limiter.allow(0) for _ in range(3)] == [True, True, False]
    assert limiter.allow(99 * MILLISECOND) is False
    assert limiter.allow(100 * MILLISECOND) is True
    assert limiter.allow(100 * MILLISECOND) is False
    assert [limiter.allow(10 * SECOND) for _ in range(3)] == [True, True, False]


def test_datagrams_keep_their_boundaries_and_name_their_sender() -> None:
    wire, left, right = pair()
    listening = right.udp.bind(5000)
    sending = left.udp.bind(0)
    messages = [b"first", b"", b"third message"]

    for message in messages:
        assert left.udp.send(sending, parse_address(PEER), 5000, message) == OK
    wire.settle()

    assert until(wire, lambda: listening.pending() == 3, MINUTE)
    taken = [listening.take() for _ in messages]
    assert [entry[2] for entry in taken if entry is not None] == messages
    assert all(
        entry is not None and entry[:2] == (parse_address(GUEST), sending.number) for entry in taken
    )
    assert sending.number >= 49152
    assert right.counters.value(UDP_DELIVERED) == 3
    assert right.budget.used_bytes == 0


def test_a_datagram_larger_than_the_link_is_fragmented_and_reassembled() -> None:
    wire, left, right = pair()
    listening = right.udp.bind(5000)
    sending = left.udp.bind(0)
    message = bytes(range(256)) * 12

    assert left.udp.send(sending, parse_address(PEER), 5000, message) == OK
    wire.settle()

    assert until(wire, lambda: listening.pending() == 1, MINUTE)
    received = listening.take()
    assert received is not None and received[2] == message
    assert right.counters.value(DATAGRAMS_REASSEMBLED) == 1
    assert right.reassembling() == 0
    fragments = [
        frame for sender, frame in wire.carried if sender == 0 and carries_a_datagram(frame)
    ]
    assert len(fragments) == 3


def test_a_datagram_to_a_port_without_listener_is_reported_to_its_sender() -> None:
    wire, left, right = pair()
    sending = left.udp.bind(0)

    assert left.udp.send(sending, parse_address(PEER), 81, b"nobody listens") == OK
    wire.settle()

    assert until(wire, lambda: sending.error != OK, MINUTE)
    assert sending.take_error() == CONNECTION_REFUSED
    assert sending.take_error() == OK
    assert right.counters.value(UDP_NO_LISTENER) == 1


def test_a_listener_that_does_not_read_holds_a_bounded_queue() -> None:
    wire, left, right = pair()
    listening = right.udp.bind(5000)
    sending = left.udp.bind(0)
    resolved = echo(wire, left, PEER)
    assert until(wire, lambda: resolved.status == OK, MINUTE)

    for index in range(UDP_QUEUE_DATAGRAMS + 4):
        assert left.udp.send(sending, parse_address(PEER), 5000, bytes((index,)) * 64) == OK
        wire.settle()
    assert until(wire, lambda: right.counters.value(UDP_QUEUE_FULL) == 4, MINUTE)

    assert listening.pending() == UDP_QUEUE_DATAGRAMS
    assert listening.dropped == 4
    assert right.budget.used_bytes == UDP_QUEUE_DATAGRAMS * 64
    right.udp.unbind(listening)
    assert right.budget.used_bytes == 0


def test_a_route_through_a_gateway_resolves_the_gateway_not_the_destination() -> None:
    left = station(0, GUEST, gateway=PEER)
    right = station(1, PEER)
    wire = Wire(left, right)

    assert left.send_echo(parse_address("192.0.2.1"), 1, b"x") == OK
    wire.settle()

    assert until(wire, lambda: left.interface.neighbors.size() == 1, MINUTE)
    assert left.interface.neighbors.entries()[0][0] == parse_address(PEER)
    assert until(wire, lambda: right.counters.value(IPV4_FOREIGN) == 1, MINUTE)


def test_without_a_gateway_a_station_off_the_link_is_unreachable_at_once() -> None:
    _wire, left, _right = pair()

    assert left.send_echo(parse_address("192.0.2.1"), 1, b"x") == UNREACHABLE
    assert left.send_echo(parse_address("224.0.0.1"), 1, b"x") == UNREACHABLE
