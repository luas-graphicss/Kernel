import pytest

from kernel_services.network.counters import (
    DATAGRAMS_REASSEMBLED,
    FRAGMENTS_EVICTED,
    FRAGMENTS_EXPIRED,
    FRAGMENTS_INVALID,
    FRAGMENTS_RECEIVED,
    Counters,
)
from kernel_services.network.ipv4.fragmentation import split
from kernel_services.network.ipv4.header import (
    HEADER_BYTES,
    MORE_FRAGMENTS,
    PROTOCOL_UDP,
    Datagram,
    decode_datagram,
    encode_datagram,
)
from kernel_services.network.ipv4.reassembly import Reassembler

SOURCE = 0x0A000202
DESTINATION = 0x0A00020F
LIFETIME = 30_000_000_000
MAX_DATAGRAMS = 4
MAX_BYTES = 4096
MTU = 576


def fragment(identification: int, offset: int, data: bytes, has_more: bool) -> Datagram:
    fragmentation = (offset // 8) | (MORE_FRAGMENTS if has_more else 0)
    return Datagram(SOURCE, DESTINATION, PROTOCOL_UDP, identification, fragmentation, data, b"")


def fragments_of(identification: int, payload: bytes, mtu: int = MTU) -> list[Datagram]:
    return [
        Datagram(SOURCE, DESTINATION, PROTOCOL_UDP, identification, fragmentation, piece, b"")
        for fragmentation, piece in split(payload, mtu)
    ]


@pytest.fixture
def counters() -> Counters:
    return Counters()


@pytest.fixture
def reassembler(counters: Counters) -> Reassembler:
    return Reassembler(MAX_DATAGRAMS, MAX_BYTES, LIFETIME, counters)


def test_pieces_fit_the_link_and_only_the_last_one_ends_the_datagram() -> None:
    payload = bytes(range(256)) * 8
    pieces = split(payload, MTU)

    assert b"".join(piece for _fragmentation, piece in pieces) == payload
    assert all(HEADER_BYTES + len(piece) <= MTU for _fragmentation, piece in pieces)
    assert all(len(piece) % 8 == 0 for _fragmentation, piece in pieces[:-1])
    assert [bool(fragmentation & MORE_FRAGMENTS) for fragmentation, _piece in pieces] == [
        True,
        True,
        True,
        False,
    ]


def test_a_datagram_header_survives_its_encoding(counters: Counters) -> None:
    encoded = encode_datagram(SOURCE, DESTINATION, PROTOCOL_UDP, 7, MORE_FRAGMENTS | 3, b"payload!")
    decoded = decode_datagram(encoded, counters)

    assert decoded is not None
    assert (decoded.source, decoded.destination, decoded.protocol) == (
        SOURCE,
        DESTINATION,
        PROTOCOL_UDP,
    )
    assert decoded.identification == 7
    assert decoded.is_fragment() and decoded.has_more_fragments()
    assert decoded.fragment_offset() == 24
    assert decoded.payload == b"payload!"


@pytest.mark.parametrize("order", [(0, 1, 2, 3), (3, 2, 1, 0), (2, 0, 3, 1)])
def test_fragments_in_any_order_join_into_the_datagram(
    reassembler: Reassembler, counters: Counters, order: tuple[int, ...]
) -> None:
    payload = bytes(range(256)) * 8
    pieces = fragments_of(1, payload)

    joined = [reassembler.add(pieces[index], 0) for index in order]

    assert joined[:-1] == [None, None, None]
    assert joined[-1] == payload
    assert reassembler.pending() == 0 and reassembler.held_bytes() == 0
    assert counters.value(DATAGRAMS_REASSEMBLED) == 1
    assert counters.value(FRAGMENTS_RECEIVED) == 4


def test_a_repeated_fragment_is_tolerated(reassembler: Reassembler, counters: Counters) -> None:
    first, second = fragments_of(2, bytes(1000))

    assert reassembler.add(first, 0) is None
    assert reassembler.add(first, 0) is None
    assert reassembler.held_bytes() == len(first.payload)
    assert reassembler.add(second, 0) == bytes(1000)
    assert counters.value(FRAGMENTS_INVALID) == 0


def test_fragments_that_overlap_with_other_bytes_invalidate_the_datagram(
    reassembler: Reassembler, counters: Counters
) -> None:
    assert reassembler.add(fragment(3, 0, b"\xaa" * 16, True), 0) is None
    assert reassembler.add(fragment(3, 8, b"\xbb" * 16, True), 0) is None

    assert counters.value(FRAGMENTS_INVALID) == 1
    assert reassembler.pending() == 0 and reassembler.held_bytes() == 0
    assert reassembler.add(fragment(3, 32, b"\xcc" * 8, False), 0) is None
    assert reassembler.pending() == 1


@pytest.mark.parametrize(
    "malformed",
    [
        fragment(4, 0, bytes(13), True),
        fragment(4, 0, b"", True),
        fragment(4, 65528, bytes(64), False),
    ],
)
def test_fragments_off_their_boundary_empty_or_past_the_end_are_refused(
    reassembler: Reassembler, counters: Counters, malformed: Datagram
) -> None:
    assert reassembler.add(malformed, 0) is None
    assert counters.value(FRAGMENTS_INVALID) == 1
    assert reassembler.pending() == 0


def test_fragments_that_disagree_about_the_end_invalidate_the_datagram(
    reassembler: Reassembler, counters: Counters
) -> None:
    assert reassembler.add(fragment(5, 16, bytes(8), False), 0) is None
    assert reassembler.add(fragment(5, 32, bytes(8), True), 0) is None

    assert counters.value(FRAGMENTS_INVALID) == 1
    assert reassembler.pending() == 0


def test_an_incomplete_datagram_expires_and_returns_its_bytes(
    reassembler: Reassembler, counters: Counters
) -> None:
    reassembler.add(fragment(6, 0, bytes(64), True), 100)

    assert reassembler.next_deadline(1 << 62) == 100 + LIFETIME
    reassembler.expire(100 + LIFETIME - 1)
    assert reassembler.pending() == 1
    reassembler.expire(100 + LIFETIME)

    assert reassembler.pending() == 0 and reassembler.held_bytes() == 0
    assert counters.value(FRAGMENTS_EXPIRED) == 1
    assert reassembler.add(fragment(6, 64, bytes(8), False), 100 + LIFETIME) is None


def test_more_datagrams_than_the_limit_evict_the_oldest(
    reassembler: Reassembler, counters: Counters
) -> None:
    for identification in range(MAX_DATAGRAMS + 2):
        reassembler.add(fragment(identification, 0, bytes(8), True), identification)

    assert reassembler.pending() == MAX_DATAGRAMS
    assert counters.value(FRAGMENTS_EVICTED) == 2
    assert reassembler.add(fragment(0, 8, bytes(8), False), 10) is None
    assert reassembler.add(fragment(5, 8, b"\x01" * 8, False), 10) == bytes(8) + b"\x01" * 8


def test_more_bytes_than_the_limit_evict_older_datagrams_first(
    reassembler: Reassembler, counters: Counters
) -> None:
    reassembler.add(fragment(1, 0, bytes(2048), True), 1)
    reassembler.add(fragment(2, 0, bytes(2048), True), 2)

    reassembler.add(fragment(3, 0, bytes(1024), True), 3)

    assert reassembler.held_bytes() == 3072
    assert counters.value(FRAGMENTS_EVICTED) == 1
    assert reassembler.add(fragment(2, 2048, bytes(8), False), 4) == bytes(2056)


def test_a_single_datagram_cannot_take_more_than_the_whole_budget(
    reassembler: Reassembler, counters: Counters
) -> None:
    reassembler.add(fragment(1, 0, bytes(2048), True), 1)
    reassembler.add(fragment(1, 2048, bytes(2048), True), 1)

    assert reassembler.add(fragment(1, 4096, bytes(8), True), 1) is None
    assert counters.value(FRAGMENTS_INVALID) == 1
    assert reassembler.held_bytes() == 0
