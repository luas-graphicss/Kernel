BITS_PER_BYTE = 8


class Bitmap:
    def __init__(self, bits: int) -> None:
        self.bits = bits
        self._bytes = bytearray((bits + BITS_PER_BYTE - 1) // BITS_PER_BYTE)

    def test(self, index: int) -> bool:
        return self._bytes[index // BITS_PER_BYTE] & (1 << index % BITS_PER_BYTE) != 0

    def set(self, index: int) -> None:
        self._bytes[index // BITS_PER_BYTE] |= 1 << index % BITS_PER_BYTE

    def clear(self, index: int) -> None:
        self._bytes[index // BITS_PER_BYTE] &= ~(1 << index % BITS_PER_BYTE) & 0xFF
