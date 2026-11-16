ADDRESS_BYTES = 6
HEADER_BYTES = 14
MINIMUM_PAYLOAD_BYTES = 46
MAXIMUM_PAYLOAD_BYTES = 1500
ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_ARP = 0x0806
BROADCAST = b"\xff\xff\xff\xff\xff\xff"
UNSPECIFIED = b"\x00\x00\x00\x00\x00\x00"
GROUP_BIT = 0x01


class Frame:
    def __init__(self, destination: bytes, source: bytes, ethertype: int, payload: bytes) -> None:
        self.destination = destination
        self.source = source
        self.ethertype = ethertype
        self.payload = payload


def is_group(address: bytes) -> bool:
    return address[0] & GROUP_BIT != 0


def is_station(address: bytes) -> bool:
    return len(address) == ADDRESS_BYTES and not is_group(address) and address != UNSPECIFIED


def decode_frame(data: bytes) -> Frame | None:
    if len(data) < HEADER_BYTES or len(data) > HEADER_BYTES + MAXIMUM_PAYLOAD_BYTES:
        return None
    source = data[ADDRESS_BYTES : 2 * ADDRESS_BYTES]
    if not is_station(source):
        return None
    ethertype = int.from_bytes(data[2 * ADDRESS_BYTES : HEADER_BYTES], "big")
    return Frame(data[:ADDRESS_BYTES], source, ethertype, data[HEADER_BYTES:])


def encode_frame(destination: bytes, source: bytes, ethertype: int, payload: bytes) -> bytes:
    padding = MINIMUM_PAYLOAD_BYTES - len(payload)
    if padding > 0:
        payload = payload + bytes(padding)
    return destination + source + ethertype.to_bytes(2, "big") + payload
