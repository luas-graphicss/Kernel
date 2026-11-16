from kernel_services.network.ipv4.checksum import ALL_ONES, complement, ones_sum
from kernel_services.network.ipv4.header import HEADER_BYTES as DATAGRAM_HEADER_BYTES
from kernel_services.network.ipv4.header import VERSION

HEADER_BYTES = 8
TYPE_ECHO_REPLY = 0
TYPE_UNREACHABLE = 3
TYPE_ECHO_REQUEST = 8
TYPE_TIME_EXCEEDED = 11
CODE_NONE = 0
CODE_HOST_UNREACHABLE = 1
CODE_PROTOCOL_UNREACHABLE = 2
CODE_PORT_UNREACHABLE = 3
CODE_FRAGMENTATION_NEEDED = 4
QUOTED_TRANSPORT_BYTES = 8
MAXIMUM_ECHO_BYTES = 1472
NO_CHECKSUM = b"\x00\x00"


class IcmpMessage:
    def __init__(self, kind: int, code: int, rest: int, body: bytes) -> None:
        self.kind = kind
        self.code = code
        self.rest = rest
        self.body = body

    def identifier(self) -> int:
        return self.rest >> 16

    def sequence(self) -> int:
        return self.rest & 0xFFFF

    def next_hop_mtu(self) -> int:
        return self.rest & 0xFFFF


class Quotation:
    def __init__(self, source: int, destination: int, protocol: int, transport: bytes) -> None:
        self.source = source
        self.destination = destination
        self.protocol = protocol
        self.transport = transport


def decode_message(payload: bytes) -> IcmpMessage | None:
    if len(payload) < HEADER_BYTES or ones_sum(payload) != ALL_ONES:
        return None
    return IcmpMessage(
        payload[0], payload[1], int.from_bytes(payload[4:8], "big"), payload[HEADER_BYTES:]
    )


def encode_message(kind: int, code: int, rest: int, body: bytes) -> bytes:
    start = bytes((kind, code))
    end = rest.to_bytes(4, "big") + body
    checksum = complement(ones_sum(start + NO_CHECKSUM + end))
    return start + checksum.to_bytes(2, "big") + end


def encode_echo(kind: int, identifier: int, sequence: int, data: bytes) -> bytes:
    return encode_message(kind, CODE_NONE, (identifier << 16) | sequence, data)


def quote(header: bytes, payload: bytes) -> bytes:
    return header + payload[:QUOTED_TRANSPORT_BYTES]


def decode_quotation(body: bytes) -> Quotation | None:
    if len(body) < DATAGRAM_HEADER_BYTES or body[0] >> 4 != VERSION:
        return None
    header_bytes = (body[0] & 0x0F) * 4
    if header_bytes < DATAGRAM_HEADER_BYTES or len(body) < header_bytes + QUOTED_TRANSPORT_BYTES:
        return None
    return Quotation(
        int.from_bytes(body[12:16], "big"),
        int.from_bytes(body[16:20], "big"),
        body[9],
        body[header_bytes : header_bytes + QUOTED_TRANSPORT_BYTES],
    )
