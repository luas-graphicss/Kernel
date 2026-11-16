from dataclasses import dataclass
from typing import TypedDict, Unpack

from kernel_tool.network import crafting
from kernel_tool.network.crafting import (
    ARP_ETHERNET,
    ARP_REQUEST,
    BROADCAST_HARDWARE,
    ETHERTYPE_ARP,
    ETHERTYPE_IPV4,
    ICMP_ECHO_REQUEST,
    ICMP_UNREACHABLE,
    PROTOCOL_ICMP,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    TCP_SYN,
    UNKNOWN_HARDWARE,
)

MORE_FRAGMENTS = 0x2000
LAST_OFFSET = 0x1FFF
UNKNOWN_HARDWARE_TYPE = 6
UNKNOWN_OPERATION = 9
PORT = 7
SOURCE_PORT = 40000
WRONG_CHECKSUM = 0x1234
ECHO_REST = b"\x00\x07\x00\x01"
NO_OPERATION_OPTIONS = b"\x01\x01\x01\x01"
OVERRUNNING_OPTION = b"\x02\x0a\x05\xb4"
EMPTY_SEGMENT_SIZE = b"\x02\x04\x00\x00"
PORT_UNREACHABLE = 3

FRAMES_MALFORMED = "frames-malformed"
ARP_MALFORMED = "arp-malformed"
IPV4_MALFORMED = "ipv4-malformed"
IPV4_BAD_CHECKSUM = "ipv4-bad-checksum"
IPV4_OPTIONS = "ipv4-options-refused"
FRAGMENTS_INVALID = "fragments-invalid"
ICMP_MALFORMED = "icmp-malformed"
UDP_MALFORMED = "udp-malformed"
UDP_BAD_CHECKSUM = "udp-bad-checksum"
TCP_MALFORMED = "tcp-malformed"
TCP_BAD_CHECKSUM = "tcp-bad-checksum"


class DatagramFields(TypedDict, total=False):
    identification: int
    fragment: int
    options: bytes
    version: int
    header_words: int
    total_bytes: int
    checksum: int


class UserDatagramFields(TypedDict, total=False):
    length: int
    checksum: int


class SegmentFields(TypedDict, total=False):
    options: bytes
    header_words: int
    checksum: int


@dataclass(frozen=True, slots=True)
class Stations:
    guest_hardware: bytes
    guest: bytes
    sender_hardware: bytes
    sender: bytes


@dataclass(frozen=True, slots=True)
class Specimen:
    name: str
    parser: str
    counter: str
    frames: tuple[bytes, ...]


class Craftsman:
    def __init__(self, stations: Stations) -> None:
        self._stations = stations

    def frame(self, ethertype: int, payload: bytes) -> bytes:
        stations = self._stations
        return crafting.ethernet(
            stations.guest_hardware, stations.sender_hardware, ethertype, payload
        )

    def resolution(self, payload: bytes) -> bytes:
        return crafting.ethernet(
            BROADCAST_HARDWARE, self._stations.sender_hardware, ETHERTYPE_ARP, payload
        )

    def request(
        self, sender_hardware: bytes, sender: bytes, hardware_type: int = ARP_ETHERNET
    ) -> bytes:
        return crafting.arp(
            ARP_REQUEST,
            sender_hardware,
            sender,
            UNKNOWN_HARDWARE,
            self._stations.guest,
            hardware_type=hardware_type,
        )

    def datagram(self, protocol: int, payload: bytes, **fields: Unpack[DatagramFields]) -> bytes:
        stations = self._stations
        packet = crafting.ipv4(stations.sender, stations.guest, protocol, payload, **fields)
        return self.frame(ETHERTYPE_IPV4, packet)

    def user_datagram(self, port: int, data: bytes, **fields: Unpack[UserDatagramFields]) -> bytes:
        stations = self._stations
        return crafting.udp(stations.sender, stations.guest, SOURCE_PORT, port, data, **fields)

    def segment(self, source_port: int, port: int, **fields: Unpack[SegmentFields]) -> bytes:
        stations = self._stations
        return crafting.tcp(
            stations.sender, stations.guest, source_port, port, 1, 0, TCP_SYN, **fields
        )


def ethernet_specimens(stations: Stations) -> tuple[Specimen, ...]:
    craftsman = Craftsman(stations)
    echo = crafting.icmp(ICMP_ECHO_REQUEST, 0, ECHO_REST, b"kernel")
    packet = crafting.ipv4(stations.sender, stations.guest, PROTOCOL_ICMP, echo)
    shortened = craftsman.frame(ETHERTYPE_IPV4, packet)[:10]
    from_group = crafting.ethernet(
        stations.guest_hardware, BROADCAST_HARDWARE, ETHERTYPE_IPV4, packet
    )
    return (
        Specimen("frame-shorter-than-its-header", "ethernet", FRAMES_MALFORMED, (shortened,)),
        Specimen("frame-sent-by-a-group-address", "ethernet", FRAMES_MALFORMED, (from_group,)),
    )


def resolution_specimens(stations: Stations) -> tuple[Specimen, ...]:
    craftsman = Craftsman(stations)
    honest = craftsman.request(stations.sender_hardware, stations.sender)
    other_type = craftsman.request(stations.sender_hardware, stations.sender, UNKNOWN_HARDWARE_TYPE)
    other_operation = crafting.arp(
        UNKNOWN_OPERATION,
        stations.sender_hardware,
        stations.sender,
        UNKNOWN_HARDWARE,
        stations.guest,
    )
    forged_sender = craftsman.request(stations.guest_hardware, stations.sender)
    claimed = craftsman.request(stations.sender_hardware, stations.guest)
    return (
        Specimen(
            "resolution-shorter-than-a-packet",
            "arp",
            ARP_MALFORMED,
            (craftsman.resolution(honest[:20]),),
        ),
        Specimen(
            "resolution-for-another-hardware",
            "arp",
            ARP_MALFORMED,
            (craftsman.resolution(other_type),),
        ),
        Specimen(
            "resolution-with-an-unknown-operation",
            "arp",
            ARP_MALFORMED,
            (craftsman.resolution(other_operation),),
        ),
        Specimen(
            "resolution-sender-differs-from-the-frame",
            "arp",
            ARP_MALFORMED,
            (craftsman.resolution(forged_sender),),
        ),
        Specimen(
            "resolution-claims-the-receiver-address",
            "arp",
            ARP_MALFORMED,
            (craftsman.resolution(claimed),),
        ),
    )


def datagram_specimens(stations: Stations) -> tuple[Specimen, ...]:
    craftsman = Craftsman(stations)
    echo = crafting.icmp(ICMP_ECHO_REQUEST, 0, ECHO_REST, b"kernel")
    return (
        Specimen(
            "datagram-of-another-version",
            "ipv4",
            IPV4_MALFORMED,
            (craftsman.datagram(PROTOCOL_ICMP, echo, version=6),),
        ),
        Specimen(
            "datagram-header-below-its-minimum",
            "ipv4",
            IPV4_MALFORMED,
            (craftsman.datagram(PROTOCOL_ICMP, echo, header_words=4),),
        ),
        Specimen(
            "datagram-longer-than-its-frame",
            "ipv4",
            IPV4_MALFORMED,
            (craftsman.datagram(PROTOCOL_ICMP, echo, total_bytes=1400),),
        ),
        Specimen(
            "datagram-shorter-than-its-header",
            "ipv4",
            IPV4_MALFORMED,
            (craftsman.datagram(PROTOCOL_ICMP, echo, total_bytes=10),),
        ),
        Specimen(
            "datagram-header-checksum-wrong",
            "ipv4",
            IPV4_BAD_CHECKSUM,
            (craftsman.datagram(PROTOCOL_ICMP, echo, checksum=WRONG_CHECKSUM),),
        ),
        Specimen(
            "datagram-with-options",
            "ipv4",
            IPV4_OPTIONS,
            (craftsman.datagram(PROTOCOL_ICMP, echo, options=NO_OPERATION_OPTIONS),),
        ),
    )


def fragment_specimens(stations: Stations) -> tuple[Specimen, ...]:
    craftsman = Craftsman(stations)

    def fragment(identification: int, offset: int, data: bytes, has_more: bool) -> bytes:
        flags = (MORE_FRAGMENTS if has_more else 0) | offset
        return craftsman.datagram(PROTOCOL_UDP, data, identification=identification, fragment=flags)

    return (
        Specimen(
            "fragment-off-the-eight-byte-boundary",
            "fragments",
            FRAGMENTS_INVALID,
            (fragment(0x4001, 0, bytes(13), True),),
        ),
        Specimen(
            "fragments-overlapping-with-other-bytes",
            "fragments",
            FRAGMENTS_INVALID,
            (
                fragment(0x4002, 0, b"\xaa" * 16, True),
                fragment(0x4002, 1, b"\xbb" * 16, True),
            ),
        ),
        Specimen(
            "fragment-past-the-largest-datagram",
            "fragments",
            FRAGMENTS_INVALID,
            (fragment(0x4003, LAST_OFFSET, bytes(64), False),),
        ),
    )


def control_specimens(stations: Stations) -> tuple[Specimen, ...]:
    craftsman = Craftsman(stations)
    echo = crafting.icmp(ICMP_ECHO_REQUEST, 0, ECHO_REST, b"kernel", checksum=WRONG_CHECKSUM)
    foreign = crafting.ipv4(stations.sender, stations.sender, PROTOCOL_UDP, bytes(8))
    report = crafting.icmp(ICMP_UNREACHABLE, PORT_UNREACHABLE, bytes(4), foreign)
    return (
        Specimen(
            "control-shorter-than-its-header",
            "icmp",
            ICMP_MALFORMED,
            (craftsman.datagram(PROTOCOL_ICMP, echo[:4]),),
        ),
        Specimen(
            "control-checksum-wrong",
            "icmp",
            ICMP_MALFORMED,
            (craftsman.datagram(PROTOCOL_ICMP, echo),),
        ),
        Specimen(
            "control-quoting-a-foreign-datagram",
            "icmp",
            ICMP_MALFORMED,
            (craftsman.datagram(PROTOCOL_ICMP, report),),
        ),
    )


def user_datagram_specimens(stations: Stations) -> tuple[Specimen, ...]:
    craftsman = Craftsman(stations)

    def carried(payload: bytes) -> tuple[bytes, ...]:
        return (craftsman.datagram(PROTOCOL_UDP, payload),)

    return (
        Specimen(
            "user-datagram-shorter-than-its-header",
            "udp",
            UDP_MALFORMED,
            carried(craftsman.user_datagram(PORT, b"")[:6]),
        ),
        Specimen(
            "user-datagram-longer-than-its-packet",
            "udp",
            UDP_MALFORMED,
            carried(craftsman.user_datagram(PORT, b"kernel", length=600, checksum=0)),
        ),
        Specimen(
            "user-datagram-length-inside-its-header",
            "udp",
            UDP_MALFORMED,
            carried(craftsman.user_datagram(PORT, b"kernel", length=4, checksum=0)),
        ),
        Specimen(
            "user-datagram-to-port-zero",
            "udp",
            UDP_MALFORMED,
            carried(craftsman.user_datagram(0, b"kernel")),
        ),
        Specimen(
            "user-datagram-checksum-wrong",
            "udp",
            UDP_BAD_CHECKSUM,
            carried(craftsman.user_datagram(PORT, b"kernel", checksum=WRONG_CHECKSUM)),
        ),
    )


def segment_specimens(stations: Stations) -> tuple[Specimen, ...]:
    craftsman = Craftsman(stations)

    def carried(payload: bytes) -> tuple[bytes, ...]:
        return (craftsman.datagram(PROTOCOL_TCP, payload),)

    return (
        Specimen(
            "segment-shorter-than-its-header",
            "tcp",
            TCP_MALFORMED,
            carried(craftsman.segment(SOURCE_PORT, PORT)[:12]),
        ),
        Specimen(
            "segment-header-below-its-minimum",
            "tcp",
            TCP_MALFORMED,
            carried(craftsman.segment(SOURCE_PORT, PORT, header_words=4)),
        ),
        Specimen(
            "segment-header-longer-than-the-segment",
            "tcp",
            TCP_MALFORMED,
            carried(craftsman.segment(SOURCE_PORT, PORT, header_words=15)),
        ),
        Specimen(
            "segment-from-port-zero",
            "tcp",
            TCP_MALFORMED,
            carried(craftsman.segment(0, PORT)),
        ),
        Specimen(
            "segment-option-past-its-header",
            "tcp",
            TCP_MALFORMED,
            carried(craftsman.segment(SOURCE_PORT, PORT, options=OVERRUNNING_OPTION)),
        ),
        Specimen(
            "segment-announcing-no-segment-size",
            "tcp",
            TCP_MALFORMED,
            carried(craftsman.segment(SOURCE_PORT, PORT, options=EMPTY_SEGMENT_SIZE)),
        ),
        Specimen(
            "segment-checksum-wrong",
            "tcp",
            TCP_BAD_CHECKSUM,
            carried(craftsman.segment(SOURCE_PORT, PORT, checksum=WRONG_CHECKSUM)),
        ),
    )


def specimens(stations: Stations) -> tuple[Specimen, ...]:
    return (
        *ethernet_specimens(stations),
        *resolution_specimens(stations),
        *datagram_specimens(stations),
        *fragment_specimens(stations),
        *control_specimens(stations),
        *user_datagram_specimens(stations),
        *segment_specimens(stations),
    )


def connection_requests(stations: Stations, port: int, count: int) -> tuple[bytes, ...]:
    craftsman = Craftsman(stations)
    return tuple(
        craftsman.datagram(PROTOCOL_TCP, craftsman.segment(SOURCE_PORT + index, port))
        for index in range(count)
    )
