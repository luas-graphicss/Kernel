from kernel_services.network.ethernet.frame import ADDRESS_BYTES, ETHERTYPE_IPV4, is_station

PACKET_BYTES = 28
HARDWARE_ETHERNET = 1
PROTOCOL_ADDRESS_BYTES = 4
OPERATION_REQUEST = 1
OPERATION_REPLY = 2
FIXED_FIELDS = (
    HARDWARE_ETHERNET.to_bytes(2, "big")
    + ETHERTYPE_IPV4.to_bytes(2, "big")
    + bytes((ADDRESS_BYTES, PROTOCOL_ADDRESS_BYTES))
)
OPERATION_FIELD = 6
SENDER_HARDWARE = 8
SENDER_PROTOCOL = 14
TARGET_HARDWARE = 18
TARGET_PROTOCOL = 24


class ArpPacket:
    def __init__(
        self,
        operation: int,
        sender_hardware: bytes,
        sender_address: int,
        target_hardware: bytes,
        target_address: int,
    ) -> None:
        self.operation = operation
        self.sender_hardware = sender_hardware
        self.sender_address = sender_address
        self.target_hardware = target_hardware
        self.target_address = target_address


def decode_packet(payload: bytes) -> ArpPacket | None:
    if len(payload) < PACKET_BYTES or payload[:OPERATION_FIELD] != FIXED_FIELDS:
        return None
    operation = int.from_bytes(payload[OPERATION_FIELD:SENDER_HARDWARE], "big")
    sender_hardware = payload[SENDER_HARDWARE:SENDER_PROTOCOL]
    if operation not in (OPERATION_REQUEST, OPERATION_REPLY) or not is_station(sender_hardware):
        return None
    return ArpPacket(
        operation,
        sender_hardware,
        int.from_bytes(payload[SENDER_PROTOCOL:TARGET_HARDWARE], "big"),
        payload[TARGET_HARDWARE:TARGET_PROTOCOL],
        int.from_bytes(payload[TARGET_PROTOCOL:PACKET_BYTES], "big"),
    )


def encode_packet(packet: ArpPacket) -> bytes:
    return (
        FIXED_FIELDS
        + packet.operation.to_bytes(2, "big")
        + packet.sender_hardware
        + packet.sender_address.to_bytes(PROTOCOL_ADDRESS_BYTES, "big")
        + packet.target_hardware
        + packet.target_address.to_bytes(PROTOCOL_ADDRESS_BYTES, "big")
    )
