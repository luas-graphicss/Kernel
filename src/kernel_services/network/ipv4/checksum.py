ALL_ONES = 0xFFFF
WORD_BITS = 16
PAD = b"\x00"


def ones_sum(data: bytes) -> int:
    if len(data) & 1:
        data = data + PAD
    value = int.from_bytes(data, "big")
    remainder = value % ALL_ONES
    if remainder == 0 and value != 0:
        return ALL_ONES
    return remainder


def combine(first: int, second: int) -> int:
    total = first + second
    return (total & ALL_ONES) + (total >> WORD_BITS)


def complement(total: int) -> int:
    return ~total & ALL_ONES


def pseudo_header_sum(source: int, destination: int, protocol: int, length: int) -> int:
    total = (source >> WORD_BITS) + (source & ALL_ONES)
    total += (destination >> WORD_BITS) + (destination & ALL_ONES)
    total += protocol + length
    while total > ALL_ONES:
        total = (total & ALL_ONES) + (total >> WORD_BITS)
    return total
