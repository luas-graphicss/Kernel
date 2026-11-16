from kernel_services.network.ipv4.header import HEADER_BYTES, MORE_FRAGMENTS, OFFSET_UNIT_BYTES


def split(payload: bytes, mtu: int) -> list[tuple[int, bytes]]:
    piece_bytes = ((mtu - HEADER_BYTES) // OFFSET_UNIT_BYTES) * OFFSET_UNIT_BYTES
    pieces = []
    offset = 0
    while offset < len(payload):
        piece = payload[offset : offset + piece_bytes]
        fragmentation = offset // OFFSET_UNIT_BYTES
        if offset + len(piece) < len(payload):
            fragmentation |= MORE_FRAGMENTS
        pieces.append((fragmentation, piece))
        offset += len(piece)
    return pieces
