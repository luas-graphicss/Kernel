from kernel_tool.network import crafting
from kernel_tool.network.crafting import (
    ETHERTYPE_IPV4,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    TCP_SYN,
    internet_checksum,
    pseudo_header,
)
from kernel_tool.network.malformed import Stations, connection_requests, specimens

GUEST = crafting.address("10.0.2.15")
SENDER = crafting.address("10.0.2.77")
STATIONS = Stations(
    guest_hardware=crafting.hardware("52:54:00:12:34:56"),
    guest=GUEST,
    sender_hardware=crafting.hardware("02:00:00:00:00:77"),
    sender=SENDER,
)
PARSERS = {"ethernet", "arp", "ipv4", "fragments", "icmp", "udp", "tcp"}


def test_addresses_are_read_from_their_usual_notation() -> None:
    assert crafting.hardware("52:54:00:12:34:56") == bytes.fromhex("525400123456")
    assert crafting.address("10.0.2.15") == bytes((10, 0, 2, 15))


def test_a_datagram_header_carries_a_checksum_that_verifies() -> None:
    datagram = crafting.ipv4(SENDER, GUEST, PROTOCOL_UDP, b"payload")

    assert internet_checksum(datagram[:20]) == 0
    assert int.from_bytes(datagram[2:4], "big") == len(datagram)
    assert datagram[9] == PROTOCOL_UDP
    assert datagram[12:20] == SENDER + GUEST


def test_overridden_fields_are_written_as_given() -> None:
    datagram = crafting.ipv4(
        SENDER, GUEST, PROTOCOL_UDP, b"payload", version=6, total_bytes=900, checksum=0x1234
    )

    assert datagram[0] >> 4 == 6
    assert int.from_bytes(datagram[2:4], "big") == 900
    assert datagram[10:12] == b"\x12\x34"


def test_transport_checksums_cover_the_pseudo_header() -> None:
    datagram = crafting.udp(SENDER, GUEST, 40000, 7, b"kernel")
    segment = crafting.tcp(SENDER, GUEST, 40000, 7, 1, 0, TCP_SYN)

    covered = pseudo_header(SENDER, GUEST, PROTOCOL_UDP, len(datagram))
    assert internet_checksum(covered + datagram) == 0
    covered = pseudo_header(SENDER, GUEST, PROTOCOL_TCP, len(segment))
    assert internet_checksum(covered + segment) == 0
    assert segment[13] == TCP_SYN


def test_every_specimen_names_a_parser_a_counter_and_its_frames() -> None:
    found = specimens(STATIONS)
    names = [specimen.name for specimen in found]

    assert len(names) == len(set(names))
    assert {specimen.parser for specimen in found} == PARSERS
    assert all(specimen.frames for specimen in found)
    assert all(specimen.counter for specimen in found)


def test_connection_requests_come_from_distinct_ports_of_one_station() -> None:
    requests = connection_requests(STATIONS, 8082, 32)
    ports = {int.from_bytes(frame[34:36], "big") for frame in requests}

    assert len(requests) == 32
    assert len(ports) == 32
    for frame in requests:
        assert frame[:6] == STATIONS.guest_hardware
        assert int.from_bytes(frame[12:14], "big") == ETHERTYPE_IPV4
        assert frame[26:30] == SENDER
        assert int.from_bytes(frame[36:38], "big") == 8082
        assert frame[47] == TCP_SYN
