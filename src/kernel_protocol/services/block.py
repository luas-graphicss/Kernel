from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_protocol.wire.message import pack_unsigned, unpack_unsigned

OPERATION_ATTACH = 16
OPERATION_READ = 17
OPERATION_WRITE = 18
OPERATION_FLUSH = 19
OPERATION_DETACH = 20
OPERATION_EVICT = 21

SECTOR_BYTES = 512
FLAG_READ_ONLY = 0x1
FLAG_FLUSH = 0x2
IDENTITY_BYTES = 20
GEOMETRY_BYTES = 44
TRANSFER_BYTES = 16
CLIENT_BYTES = 8


class Geometry:
    def __init__(self, sectors: int, flags: int, instance: int, identity: bytes) -> None:
        self.sectors = sectors
        self.flags = flags
        self.instance = instance
        self.identity = identity


def encode_geometry(geometry: Geometry) -> bytes:
    identity = geometry.identity[:IDENTITY_BYTES]
    return (
        pack_unsigned(geometry.sectors, 8)
        + pack_unsigned(SECTOR_BYTES, 4)
        + pack_unsigned(geometry.flags, 4)
        + pack_unsigned(geometry.instance, 8)
        + identity
        + bytes(IDENTITY_BYTES - len(identity))
    )


def decode_geometry(payload: bytes) -> Geometry:
    if len(payload) != GEOMETRY_BYTES or unpack_unsigned(payload, 8, 12) != SECTOR_BYTES:
        raise KernelError(INVALID_ARGUMENT, "block service described an unknown geometry")
    return Geometry(
        sectors=unpack_unsigned(payload, 0, 8),
        flags=unpack_unsigned(payload, 12, 16),
        instance=unpack_unsigned(payload, 16, 24),
        identity=payload[24:].rstrip(b"\x00"),
    )


def encode_transfer(sector: int, count: int, offset: int) -> bytes:
    return pack_unsigned(sector, 8) + pack_unsigned(count, 4) + pack_unsigned(offset, 4)


def decode_transfer(payload: bytes) -> tuple[int, int, int]:
    if len(payload) != TRANSFER_BYTES:
        raise KernelError(INVALID_ARGUMENT, "block transfer has the wrong size")
    return (
        unpack_unsigned(payload, 0, 8),
        unpack_unsigned(payload, 8, 12),
        unpack_unsigned(payload, 12, 16),
    )


def encode_client(identity: int) -> bytes:
    return pack_unsigned(identity, CLIENT_BYTES)


def decode_client(payload: bytes) -> int:
    if len(payload) != CLIENT_BYTES:
        raise KernelError(INVALID_ARGUMENT, "client identity has the wrong size")
    return unpack_unsigned(payload, 0, CLIENT_BYTES)
