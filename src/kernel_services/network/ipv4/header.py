from kernel_services.network.counters import (
    IPV4_BAD_CHECKSUM,
    IPV4_BAD_SOURCE,
    IPV4_MALFORMED,
    IPV4_OPTIONS,
    Counters,
)
from kernel_services.network.ipv4.address import is_host
from kernel_services.network.ipv4.checksum import ALL_ONES, complement, ones_sum

VERSION = 4
HEADER_BYTES = 20
HEADER_WORDS = 5
MAXIMUM_DATAGRAM_BYTES = 65535
PROTOCOL_ICMP = 1
PROTOCOL_TCP = 6
PROTOCOL_UDP = 17
DONT_FRAGMENT = 0x4000
MORE_FRAGMENTS = 0x2000
OFFSET_MASK = 0x1FFF
OFFSET_UNIT_BYTES = 8
DEFAULT_TTL = 64
VERSION_AND_LENGTH = (VERSION << 4) | HEADER_WORDS
NO_SERVICE = 0
NO_CHECKSUM = b"\x00\x00"


class Datagram:
    def __init__(
        self,
        source: int,
        destination: int,
        protocol: int,
        identification: int,
        fragmentation: int,
        payload: bytes,
        header: bytes,
    ) -> None:
        self.source = source
        self.destination = destination
        self.protocol = protocol
        self.identification = identification
        self.fragmentation = fragmentation
        self.payload = payload
        self.header = header

    def is_fragment(self) -> bool:
        return self.fragmentation & (MORE_FRAGMENTS | OFFSET_MASK) != 0

    def fragment_offset(self) -> int:
        return (self.fragmentation & OFFSET_MASK) * OFFSET_UNIT_BYTES

    def has_more_fragments(self) -> bool:
        return self.fragmentation & MORE_FRAGMENTS != 0


def decode_datagram(data: bytes, counters: Counters) -> Datagram | None:
    if len(data) < HEADER_BYTES or data[0] >> 4 != VERSION:
        counters.count(IPV4_MALFORMED)
        return None
    header_bytes = (data[0] & 0x0F) * 4
    total_bytes = int.from_bytes(data[2:4], "big")
    if header_bytes < HEADER_BYTES or total_bytes < header_bytes or total_bytes > len(data):
        counters.count(IPV4_MALFORMED)
        return None
    if header_bytes != HEADER_BYTES:
        counters.count(IPV4_OPTIONS)
        return None
    header = data[:HEADER_BYTES]
    if ones_sum(header) != ALL_ONES:
        counters.count(IPV4_BAD_CHECKSUM)
        return None
    source = int.from_bytes(header[12:16], "big")
    if not is_host(source):
        counters.count(IPV4_BAD_SOURCE)
        return None
    return Datagram(
        source,
        int.from_bytes(header[16:20], "big"),
        header[9],
        int.from_bytes(header[4:6], "big"),
        int.from_bytes(header[6:8], "big"),
        data[HEADER_BYTES:total_bytes],
        header,
    )


def encode_datagram(
    source: int,
    destination: int,
    protocol: int,
    identification: int,
    fragmentation: int,
    payload: bytes,
    ttl: int = DEFAULT_TTL,
) -> bytes:
    start = (
        bytes((VERSION_AND_LENGTH, NO_SERVICE))
        + (HEADER_BYTES + len(payload)).to_bytes(2, "big")
        + identification.to_bytes(2, "big")
        + fragmentation.to_bytes(2, "big")
        + bytes((ttl, protocol))
    )
    addresses = source.to_bytes(4, "big") + destination.to_bytes(4, "big")
    checksum = complement(ones_sum(start + NO_CHECKSUM + addresses))
    return start + checksum.to_bytes(2, "big") + addresses + payload
