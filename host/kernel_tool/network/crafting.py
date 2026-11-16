import socket
import struct

ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_ARP = 0x0806
PROTOCOL_ICMP = 1
PROTOCOL_TCP = 6
PROTOCOL_UDP = 17
ARP_REQUEST = 1
ARP_REPLY = 2
ARP_ETHERNET = 1
ICMP_ECHO_REQUEST = 8
ICMP_UNREACHABLE = 3
TCP_FIN = 0x01
TCP_SYN = 0x02
TCP_ACK = 0x10
HARDWARE_BYTES = 6
ADDRESS_BYTES = 4
IPV4_HEADER_BYTES = 20
UDP_HEADER_BYTES = 8
TCP_HEADER_BYTES = 20
WORD_BYTES = 4
TIME_TO_LIVE = 64
FULL_WINDOW = 0xFFFF
CHECKSUM_MASK = 0xFFFF
BROADCAST_HARDWARE = b"\xff" * HARDWARE_BYTES
UNKNOWN_HARDWARE = bytes(HARDWARE_BYTES)


def hardware(text: str) -> bytes:
    return bytes.fromhex(text.replace(":", ""))


def address(text: str) -> bytes:
    return socket.inet_aton(text)


def internet_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total: int = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & CHECKSUM_MASK) + (total >> 16)
    return ~total & CHECKSUM_MASK


def pseudo_header(source: bytes, destination: bytes, protocol: int, length: int) -> bytes:
    return source + destination + struct.pack("!BBH", 0, protocol, length)


def ethernet(destination: bytes, source: bytes, ethertype: int, payload: bytes) -> bytes:
    return destination + source + struct.pack("!H", ethertype) + payload


def arp(
    operation: int,
    sender_hardware: bytes,
    sender: bytes,
    target_hardware: bytes,
    target: bytes,
    *,
    hardware_type: int = ARP_ETHERNET,
) -> bytes:
    fixed = struct.pack(
        "!HHBBH", hardware_type, ETHERTYPE_IPV4, HARDWARE_BYTES, ADDRESS_BYTES, operation
    )
    return fixed + sender_hardware + sender + target_hardware + target


def ipv4(
    source: bytes,
    destination: bytes,
    protocol: int,
    payload: bytes,
    *,
    identification: int = 0,
    fragment: int = 0,
    options: bytes = b"",
    version: int = 4,
    header_words: int | None = None,
    total_bytes: int | None = None,
    checksum: int | None = None,
) -> bytes:
    header_bytes = IPV4_HEADER_BYTES + len(options)
    words = header_bytes // WORD_BYTES if header_words is None else header_words
    total = header_bytes + len(payload) if total_bytes is None else total_bytes

    def header(value: int) -> bytes:
        fixed = struct.pack(
            "!BBHHHBBH",
            (version << 4) | words,
            0,
            total,
            identification,
            fragment,
            TIME_TO_LIVE,
            protocol,
            value,
        )
        return fixed + source + destination + options

    value = internet_checksum(header(0)) if checksum is None else checksum
    return header(value) + payload


def icmp(kind: int, code: int, rest: bytes, body: bytes, *, checksum: int | None = None) -> bytes:
    def message(value: int) -> bytes:
        return struct.pack("!BBH", kind, code, value) + rest + body

    return message(internet_checksum(message(0)) if checksum is None else checksum)


def udp(
    source: bytes,
    destination: bytes,
    source_port: int,
    destination_port: int,
    data: bytes,
    *,
    length: int | None = None,
    checksum: int | None = None,
) -> bytes:
    size = UDP_HEADER_BYTES + len(data) if length is None else length

    def datagram(value: int) -> bytes:
        return struct.pack("!HHHH", source_port, destination_port, size, value) + data

    if checksum is None:
        covered = pseudo_header(source, destination, PROTOCOL_UDP, len(datagram(0)))
        checksum = internet_checksum(covered + datagram(0)) or CHECKSUM_MASK
    return datagram(checksum)


def tcp(
    source: bytes,
    destination: bytes,
    source_port: int,
    destination_port: int,
    sequence: int,
    acknowledgment: int,
    flags: int,
    *,
    options: bytes = b"",
    data: bytes = b"",
    header_words: int | None = None,
    checksum: int | None = None,
) -> bytes:
    words = (
        (TCP_HEADER_BYTES + len(options)) // WORD_BYTES if header_words is None else header_words
    )

    def segment(value: int) -> bytes:
        fixed = struct.pack(
            "!HHIIBBHHH",
            source_port,
            destination_port,
            sequence,
            acknowledgment,
            words << 4,
            flags,
            FULL_WINDOW,
            value,
            0,
        )
        return fixed + options + data

    if checksum is None:
        covered = pseudo_header(source, destination, PROTOCOL_TCP, len(segment(0)))
        checksum = internet_checksum(covered + segment(0))
    return segment(checksum)
