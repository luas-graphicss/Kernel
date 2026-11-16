from kernel_services.network.counters import TCP_BAD_CHECKSUM, TCP_MALFORMED, Counters
from kernel_services.network.ipv4.checksum import (
    ALL_ONES,
    combine,
    complement,
    ones_sum,
    pseudo_header_sum,
)
from kernel_services.network.ipv4.header import PROTOCOL_TCP

HEADER_BYTES = 20
FLAG_FIN = 0x01
FLAG_SYN = 0x02
FLAG_RST = 0x04
FLAG_PSH = 0x08
FLAG_ACK = 0x10
OPTION_END = 0
OPTION_NO_OPERATION = 1
OPTION_SEGMENT_SIZE = 2
SEGMENT_SIZE_OPTION_BYTES = 4
MAXIMUM_WINDOW = 0xFFFF
NO_SEGMENT_SIZE = 0
NO_CHECKSUM_OR_URGENT = b"\x00\x00\x00\x00"
PLAIN_OFFSET = (HEADER_BYTES // 4) << 4
OPTION_OFFSET = ((HEADER_BYTES + SEGMENT_SIZE_OPTION_BYTES) // 4) << 4
MALFORMED_OPTIONS = -1


class Segment:
    def __init__(
        self,
        source_port: int,
        destination_port: int,
        sequence: int,
        acknowledgment: int,
        flags: int,
        window: int,
        segment_size: int,
        data: bytes,
    ) -> None:
        self.source_port = source_port
        self.destination_port = destination_port
        self.sequence = sequence
        self.acknowledgment = acknowledgment
        self.flags = flags
        self.window = window
        self.segment_size = segment_size
        self.data = data

    def has(self, flag: int) -> bool:
        return self.flags & flag != 0

    def length(self) -> int:
        length = len(self.data)
        if self.flags & FLAG_SYN:
            length += 1
        if self.flags & FLAG_FIN:
            length += 1
        return length


def announced_segment_size(options: bytes) -> int:
    position = 0
    announced = NO_SEGMENT_SIZE
    while position < len(options):
        kind = options[position]
        if kind == OPTION_END:
            break
        if kind == OPTION_NO_OPERATION:
            position += 1
            continue
        if position + 1 >= len(options):
            return MALFORMED_OPTIONS
        size = options[position + 1]
        if size < 2 or position + size > len(options):
            return MALFORMED_OPTIONS
        if kind == OPTION_SEGMENT_SIZE:
            if size != SEGMENT_SIZE_OPTION_BYTES:
                return MALFORMED_OPTIONS
            announced = int.from_bytes(options[position + 2 : position + 4], "big")
            if announced == NO_SEGMENT_SIZE:
                return MALFORMED_OPTIONS
        position += size
    return announced


def decode_segment(
    payload: bytes, source: int, destination: int, counters: Counters
) -> Segment | None:
    if len(payload) < HEADER_BYTES:
        counters.count(TCP_MALFORMED)
        return None
    header_bytes = (payload[12] >> 4) * 4
    source_port = int.from_bytes(payload[0:2], "big")
    destination_port = int.from_bytes(payload[2:4], "big")
    if header_bytes < HEADER_BYTES or header_bytes > len(payload):
        counters.count(TCP_MALFORMED)
        return None
    if source_port == 0 or destination_port == 0:
        counters.count(TCP_MALFORMED)
        return None
    covered = pseudo_header_sum(source, destination, PROTOCOL_TCP, len(payload))
    if combine(covered, ones_sum(payload)) != ALL_ONES:
        counters.count(TCP_BAD_CHECKSUM)
        return None
    segment_size = announced_segment_size(payload[HEADER_BYTES:header_bytes])
    if segment_size == MALFORMED_OPTIONS:
        counters.count(TCP_MALFORMED)
        return None
    return Segment(
        source_port,
        destination_port,
        int.from_bytes(payload[4:8], "big"),
        int.from_bytes(payload[8:12], "big"),
        payload[13] & 0x3F,
        int.from_bytes(payload[14:16], "big"),
        segment_size,
        payload[header_bytes:],
    )


def encode_segment(source: int, destination: int, segment: Segment) -> bytes:
    options = b""
    offset = PLAIN_OFFSET
    if segment.segment_size != NO_SEGMENT_SIZE:
        options = bytes((OPTION_SEGMENT_SIZE, SEGMENT_SIZE_OPTION_BYTES))
        options += segment.segment_size.to_bytes(2, "big")
        offset = OPTION_OFFSET
    start = (
        segment.source_port.to_bytes(2, "big")
        + segment.destination_port.to_bytes(2, "big")
        + segment.sequence.to_bytes(4, "big")
        + segment.acknowledgment.to_bytes(4, "big")
        + bytes((offset, segment.flags))
        + segment.window.to_bytes(2, "big")
    )
    end = options + segment.data
    length = len(start) + len(NO_CHECKSUM_OR_URGENT) + len(end)
    covered = pseudo_header_sum(source, destination, PROTOCOL_TCP, length)
    checksum = complement(combine(covered, ones_sum(start + NO_CHECKSUM_OR_URGENT + end)))
    return start + checksum.to_bytes(2, "big") + b"\x00\x00" + end
