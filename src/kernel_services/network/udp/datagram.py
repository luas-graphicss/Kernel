from kernel_services.network.counters import UDP_BAD_CHECKSUM, UDP_MALFORMED, Counters
from kernel_services.network.ipv4.checksum import (
    ALL_ONES,
    combine,
    complement,
    ones_sum,
    pseudo_header_sum,
)
from kernel_services.network.ipv4.header import PROTOCOL_UDP

HEADER_BYTES = 8
MAXIMUM_DATA_BYTES = 65507
NO_CHECKSUM = b"\x00\x00"


class UdpDatagram:
    def __init__(self, source_port: int, destination_port: int, data: bytes) -> None:
        self.source_port = source_port
        self.destination_port = destination_port
        self.data = data


def decode_datagram(
    payload: bytes, source: int, destination: int, counters: Counters
) -> UdpDatagram | None:
    if len(payload) < HEADER_BYTES:
        counters.count(UDP_MALFORMED)
        return None
    length = int.from_bytes(payload[4:6], "big")
    destination_port = int.from_bytes(payload[2:4], "big")
    if length < HEADER_BYTES or length > len(payload) or destination_port == 0:
        counters.count(UDP_MALFORMED)
        return None
    if length < len(payload):
        payload = payload[:length]
    if payload[6:8] != NO_CHECKSUM:
        covered = pseudo_header_sum(source, destination, PROTOCOL_UDP, length)
        if combine(covered, ones_sum(payload)) != ALL_ONES:
            counters.count(UDP_BAD_CHECKSUM)
            return None
    return UdpDatagram(
        int.from_bytes(payload[0:2], "big"), destination_port, payload[HEADER_BYTES:]
    )


def encode_datagram(
    source: int, destination: int, source_port: int, destination_port: int, data: bytes
) -> bytes:
    length = HEADER_BYTES + len(data)
    start = (
        source_port.to_bytes(2, "big")
        + destination_port.to_bytes(2, "big")
        + length.to_bytes(2, "big")
    )
    covered = pseudo_header_sum(source, destination, PROTOCOL_UDP, length)
    checksum = complement(combine(covered, ones_sum(start + NO_CHECKSUM + data)))
    if checksum == 0:
        checksum = ALL_ONES
    return start + checksum.to_bytes(2, "big") + data
