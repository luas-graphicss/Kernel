import hashlib
import itertools

import pytest

from doubles.links import (
    ABSENT,
    PORT,
    carry,
    connect,
    impaired,
    pair,
    silence_from,
    until,
)
from doubles.wire import MILLISECOND, MTU, PREFIX, SECOND, Wire, deliver_once
from kernel_protocol.errors.codes import (
    CONNECTION_REFUSED,
    CONNECTION_RESET,
    OK,
    TIMED_OUT,
    UNREACHABLE,
)
from kernel_services.network.counters import (
    ARP_UNRESOLVED,
    TCP_BACKLOG_FULL,
    TCP_CONNECTIONS_FAILED,
    TCP_OUT_OF_ORDER,
    TCP_RESETS_SENT,
    TCP_RETRANSMITTED,
)
from kernel_services.network.ethernet.frame import ETHERTYPE_IPV4, decode_frame, encode_frame
from kernel_services.network.ipv4.address import parse_address
from kernel_services.network.ipv4.header import PROTOCOL_TCP, encode_datagram
from kernel_services.network.ipv4.routing import NO_GATEWAY, checked_route
from kernel_services.network.limits import (
    TCP_RECEIVE_BYTES,
    TCP_RETRANSMISSIONS,
    TCP_SEGMENT_LIFETIME_NANOSECONDS,
    TCP_SEND_BYTES,
)
from kernel_services.network.stack import Stack
from kernel_services.network.tcp.connection import (
    CLOSE_WAIT,
    CLOSED,
    ESTABLISHED,
    FIN_WAIT_2,
    SYN_SENT,
    TIME_WAIT,
)
from kernel_services.network.tcp.segment import (
    FLAG_ACK,
    FLAG_SYN,
    NO_SEGMENT_SIZE,
    Segment,
    encode_segment,
)

MINUTE = 60 * SECOND
INTRUDER = parse_address("10.0.2.77")
INTRUDER_HARDWARE = bytes((0x02, 0, 0, 0, 0, 0x77))
SMALL_MTU = 576
IP_AND_TCP_HEADERS = 40


def pattern(length: int, seed: int) -> bytes:
    block = hashlib.sha256(seed.to_bytes(4, "big")).digest()
    return (block * (length // len(block) + 1))[:length]


def last_sequences(count: int) -> bytes:
    return b"\xff" * count


def tcp_frame(receiver: Stack, source: int, segment: Segment) -> bytes:
    local = receiver.interface.route.address
    datagram = encode_datagram(
        source, local, PROTOCOL_TCP, 1, 0, encode_segment(source, local, segment)
    )
    return encode_frame(receiver.interface.hardware, INTRUDER_HARDWARE, ETHERTYPE_IPV4, datagram)


def data_bytes_of(wire: Wire, sender: int) -> list[int]:
    sizes = []
    for index, frame in wire.carried:
        decoded = decode_frame(frame)
        if index != sender or decoded is None or decoded.ethertype != ETHERTYPE_IPV4:
            continue
        total = int.from_bytes(decoded.payload[2:4], "big")
        if total > IP_AND_TCP_HEADERS + 4:
            sizes.append(total)
    return sizes


def test_a_connection_opens_with_a_handshake_and_both_sides_agree_on_it() -> None:
    wire, client, server = pair()

    opened, accepted = connect(wire, client, server)

    assert opened.state == ESTABLISHED and accepted.state == ESTABLISHED
    assert accepted.is_passive and not opened.is_passive
    assert (opened.remote_port, accepted.local_port) == (PORT, PORT)
    assert opened.local_port == accepted.remote_port
    assert opened.local_port >= 49152
    assert client.tcp.connection_count() == 1 and server.tcp.connection_count() == 1


def test_bytes_cross_in_both_directions_in_the_order_they_were_written() -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    upward = pattern(50000, 1)
    downward = pattern(30000, 2)

    assert carry(wire, opened, accepted, upward, MINUTE) == upward
    assert carry(wire, accepted, opened, downward, MINUTE) == downward
    assert client.counters.value(TCP_RETRANSMITTED) == 0
    assert until(
        wire, lambda: client.budget.used_bytes == 0 and server.budget.used_bytes == 0, MINUTE
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_a_transfer_survives_loss_duplication_and_reordering(seed: int) -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    wire.fate = impaired(seed, loss=0.05, duplicate=0.05, reorder=0.2)
    upward = pattern(120000, seed)
    downward = pattern(60000, seed + 100)

    assert carry(wire, opened, accepted, upward, 30 * MINUTE) == upward
    assert carry(wire, accepted, opened, downward, 30 * MINUTE) == downward
    assert client.counters.value(TCP_RETRANSMITTED) > 0
    assert server.counters.value(TCP_OUT_OF_ORDER) > 0
    assert opened.state == ESTABLISHED and accepted.state == ESTABLISHED


def test_sequence_numbers_wrap_around_without_losing_or_repeating_bytes() -> None:
    client = Stack(b"\x02\x00\x00\x00\x00\x01", route("10.0.2.15"), MTU, last_sequences)
    server = Stack(b"\x02\x00\x00\x00\x00\x02", route("10.0.2.2"), MTU, last_sequences)
    wire = Wire(client, server)
    wire.fate = impaired(9, loss=0.03, duplicate=0.03, reorder=0.1)
    opened, accepted = connect(wire, client, server)
    data = pattern(90000, 7)

    assert carry(wire, opened, accepted, data, 30 * MINUTE) == data
    assert carry(wire, accepted, opened, data, 30 * MINUTE) == data


def route(address: str):
    return checked_route(parse_address(address), PREFIX, NO_GATEWAY)


def test_a_peer_that_never_reads_stops_the_sender_inside_its_buffers() -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    data = pattern(200000, 3)
    written = 0

    def stalled() -> bool:
        nonlocal written
        accepted_bytes = opened.write(data[written : written + 4096], wire.now)
        written += accepted_bytes
        wire.settle()
        return accepted_bytes == 0 and wire.now > 5 * SECOND

    assert wire.run_until(stalled, MINUTE)
    assert 0 < written <= TCP_SEND_BYTES + TCP_RECEIVE_BYTES
    assert accepted.readable_bytes() <= TCP_RECEIVE_BYTES
    assert opened.unacknowledged_bytes() <= TCP_SEND_BYTES
    assert client.budget.used_bytes <= TCP_SEND_BYTES
    assert opened.state == ESTABLISHED and opened.error == OK


def test_reading_reopens_a_closed_window_and_the_rest_arrives() -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    data = pattern(3 * TCP_RECEIVE_BYTES, 4)
    written = opened.write(data, wire.now)
    wire.settle()
    assert wire.run_until(lambda: accepted.readable_bytes() == TCP_RECEIVE_BYTES, MINUTE)
    wire.advance(10 * SECOND)

    assert carry(wire, opened, accepted, data[written:], 5 * MINUTE)[-64:] == data[-64:]
    assert until(wire, lambda: opened.unacknowledged_bytes() == 0, MINUTE)


def test_an_unanswered_segment_is_retransmitted_with_a_growing_timeout() -> None:
    wire, client, server = pair()
    opened, _accepted = connect(wire, client, server)
    wire.fate = silence_from(0)
    opened.write(b"lost in the dark", wire.now)
    wire.settle()
    sent_at = [wire.now]

    def record(sender: int, _frame: bytes) -> list[int]:
        if sender == 0:
            sent_at.append(wire.now)
        return []

    wire.fate = record
    assert until(wire, lambda: opened.state == CLOSED, 60 * MINUTE)
    gaps = [later - earlier for earlier, later in itertools.pairwise(sent_at)]
    retransmissions = gaps[:TCP_RETRANSMISSIONS]

    assert len(retransmissions) == TCP_RETRANSMISSIONS
    assert all(later >= earlier for earlier, later in itertools.pairwise(retransmissions))
    assert retransmissions[-1] > retransmissions[0]
    assert opened.error == TIMED_OUT
    assert client.counters.value(TCP_RETRANSMITTED) == TCP_RETRANSMISSIONS
    assert client.tcp.connection_count() == 0 and client.budget.used_bytes == 0


def test_a_port_without_a_listener_refuses_the_connection_with_a_reset() -> None:
    wire, client, server = pair()

    refused = client.tcp.connect(server.interface.route.address, 81, wire.now)
    wire.settle()

    assert until(wire, lambda: refused.state == CLOSED, MINUTE)
    assert refused.error == CONNECTION_REFUSED
    assert server.counters.value(TCP_RESETS_SENT) == 1
    assert client.counters.value(TCP_CONNECTIONS_FAILED) == 1
    assert client.tcp.connection_count() == 0


def test_a_reset_ends_an_established_connection_on_the_other_side() -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    opened.write(b"unread", wire.now)
    wire.settle()
    assert until(wire, lambda: accepted.readable_bytes() == 6, MINUTE)

    server.tcp.release(accepted)

    assert until(wire, lambda: opened.state == CLOSED, MINUTE)
    assert opened.error == CONNECTION_RESET
    assert server.budget.used_bytes == 0 and client.budget.used_bytes == 0


def test_a_half_closed_connection_still_carries_the_other_direction() -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    opened.write(b"request", wire.now)
    opened.finish(wire.now)
    wire.settle()

    assert until(wire, lambda: accepted.state == CLOSE_WAIT, MINUTE)
    assert accepted.read(100) == b"request" and accepted.is_at_end_of_input()
    assert until(wire, lambda: opened.state == FIN_WAIT_2, MINUTE)
    assert not opened.is_writable()
    answer = pattern(20000, 5)
    assert carry(wire, accepted, opened, answer, MINUTE) == answer
    accepted.finish(wire.now)
    assert until(wire, lambda: accepted.state == CLOSED and opened.state == TIME_WAIT, MINUTE)
    assert opened.is_at_end_of_input() and opened.error == OK and accepted.error == OK


def test_the_side_that_closes_first_lingers_before_it_forgets_the_connection() -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    opened.finish(wire.now)
    wire.settle()
    assert until(wire, lambda: accepted.state == CLOSE_WAIT, MINUTE)
    accepted.finish(wire.now)
    assert until(wire, lambda: opened.state == TIME_WAIT, MINUTE)
    lingering_since = wire.now

    assert client.tcp.connection_count() == 0
    assert until(wire, lambda: server.tcp.connection_count() == 0, MINUTE)
    assert accepted.state == CLOSED
    wire.advance(2 * TCP_SEGMENT_LIFETIME_NANOSECONDS - 2 * SECOND)
    assert opened.state == TIME_WAIT
    assert until(wire, lambda: opened.state == CLOSED, MINUTE)
    assert wire.now - lingering_since >= 2 * TCP_SEGMENT_LIFETIME_NANOSECONDS
    assert opened.error == OK


def test_an_acknowledgment_of_bytes_never_sent_changes_nothing() -> None:
    wire, client, server = pair()
    opened, accepted = connect(wire, client, server)
    wire.fate = silence_from(0)
    opened.write(b"waiting for its acknowledgment", wire.now)
    wire.settle()
    pending = opened.unacknowledged_bytes()
    forged = Segment(PORT, opened.local_port, 1, 0x7FFFFFFF, FLAG_ACK, 4096, NO_SEGMENT_SIZE, b"")
    frame = tcp_frame(client, server.interface.route.address, forged)

    wire.inject(0, frame)

    assert opened.state == ESTABLISHED and opened.error == OK
    assert opened.unacknowledged_bytes() == pending
    assert accepted.state == ESTABLISHED


def test_connection_requests_beyond_the_backlog_are_dropped_and_counted() -> None:
    wire, _client, server = pair()
    listener = server.tcp.listen(8082, 2)
    for index in range(6):
        request = Segment(40000 + index, 8082, 100, 0, FLAG_SYN, 4096, 1460, b"")
        wire.inject(1, tcp_frame(server, INTRUDER, request))

    assert server.counters.value(TCP_BACKLOG_FULL) == 4
    assert server.tcp.connection_count() == 2
    assert listener.accept() is None
    assert server.budget.used_bytes == 0
    server.tcp.stop_listening(listener)
    assert server.tcp.connection_count() == 0


def test_a_smaller_segment_size_announced_by_the_peer_is_respected() -> None:
    wire, client, server = pair(right_mtu=SMALL_MTU)
    opened, accepted = connect(wire, client, server)
    data = pattern(20000, 6)

    assert carry(wire, opened, accepted, data, MINUTE) == data
    assert max(data_bytes_of(wire, 0)) == SMALL_MTU
    assert carry(wire, accepted, opened, data, MINUTE) == data
    assert max(data_bytes_of(wire, 1)) == SMALL_MTU


def test_a_next_hop_that_never_resolves_fails_the_connection_being_opened() -> None:
    wire, client, _server = pair()

    lost = client.tcp.connect(parse_address(ABSENT), PORT, wire.now)
    wire.settle()
    assert lost.state == SYN_SENT

    assert until(wire, lambda: lost.state == CLOSED, MINUTE)
    assert lost.error == UNREACHABLE
    assert wire.now < 5 * SECOND
    assert client.counters.value(ARP_UNRESOLVED) == 1
    assert client.tcp.connection_count() == 0


def test_a_delivered_frame_takes_the_propagation_delay_of_the_wire() -> None:
    wire, client, server = pair()
    assert wire.fate is deliver_once

    connect(wire, client, server)

    assert 0 < wire.now < 100 * MILLISECOND
