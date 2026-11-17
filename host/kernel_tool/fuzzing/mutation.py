import random
from collections.abc import Callable
from typing import Literal

INTERESTING_BYTES = (0x00, 0x01, 0x7F, 0x80, 0xFF)
INTERESTING_INTEGERS = (
    0,
    1,
    0x7F,
    0x80,
    0xFF,
    0x100,
    0x7FFF,
    0x8000,
    0xFFFF,
    0x1_0000,
    0x7FFF_FFFF,
    0x8000_0000,
    0xFFFF_FFFF,
    0x1_0000_0000,
    0x7FFF_FFFF_FFFF_FFFF,
    0xFFFF_FFFF_FFFF_FFFF,
)
FIELD_WIDTHS = (1, 2, 4, 8)
BYTE_ORDERS: tuple[Literal["little", "big"], ...] = ("little", "big")
MAX_STACKED_EDITS = 4
MAX_CHUNK_BYTES = 64
MAX_DELTA = 16
BITS_PER_BYTE = 8
BYTE_VALUES = 256

type Edit = Callable[[bytearray, bytes], None]


class Mutator:
    def __init__(self, chooser: random.Random, max_bytes: int) -> None:
        self._chooser = chooser
        self._max_bytes = max_bytes
        self._edits: tuple[Edit, ...] = (
            self._flip_bit,
            self._set_byte,
            self._set_field,
            self._shift_field,
            self._insert,
            self._delete,
            self._duplicate,
            self._splice,
            self._truncate,
        )

    def mutate(self, parent: bytes, donor: bytes) -> bytes:
        data = bytearray(parent)
        for _ in range(self._chooser.randint(1, MAX_STACKED_EDITS)):
            self._chooser.choice(self._edits)(data, donor)
        return bytes(data[: self._max_bytes])

    def _position(self, data: bytearray) -> int:
        return self._chooser.randrange(len(data)) if data else 0

    def _field(self, data: bytearray) -> tuple[int, int] | None:
        widths = [width for width in FIELD_WIDTHS if width <= len(data)]
        if not widths:
            return None
        width = self._chooser.choice(widths)
        return self._chooser.randrange(len(data) - width + 1), width

    def _flip_bit(self, data: bytearray, _donor: bytes) -> None:
        if data:
            data[self._position(data)] ^= 1 << self._chooser.randrange(BITS_PER_BYTE)

    def _set_byte(self, data: bytearray, _donor: bytes) -> None:
        value = self._chooser.choice((*INTERESTING_BYTES, self._chooser.randrange(BYTE_VALUES)))
        if data:
            data[self._position(data)] = value
        else:
            data.append(value)

    def _set_field(self, data: bytearray, _donor: bytes) -> None:
        field = self._field(data)
        if field is None:
            return
        start, width = field
        limit = 1 << (width * BITS_PER_BYTE)
        value = self._chooser.choice((*INTERESTING_INTEGERS, len(data))) % limit
        data[start : start + width] = value.to_bytes(width, self._chooser.choice(BYTE_ORDERS))

    def _shift_field(self, data: bytearray, _donor: bytes) -> None:
        field = self._field(data)
        if field is None:
            return
        start, width = field
        order = self._chooser.choice(BYTE_ORDERS)
        limit = 1 << (width * BITS_PER_BYTE)
        delta = self._chooser.randint(-MAX_DELTA, MAX_DELTA)
        value = (int.from_bytes(data[start : start + width], order) + delta) % limit
        data[start : start + width] = value.to_bytes(width, order)

    def _insert(self, data: bytearray, _donor: bytes) -> None:
        count = self._chooser.randint(1, MAX_CHUNK_BYTES)
        filler = self._chooser.choice(INTERESTING_BYTES)
        position = self._chooser.randint(0, len(data))
        data[position:position] = bytes((filler,)) * count

    def _delete(self, data: bytearray, _donor: bytes) -> None:
        if not data:
            return
        start = self._position(data)
        del data[start : start + self._chooser.randint(1, MAX_CHUNK_BYTES)]

    def _duplicate(self, data: bytearray, _donor: bytes) -> None:
        if not data:
            return
        start = self._position(data)
        chunk = data[start : start + self._chooser.randint(1, MAX_CHUNK_BYTES)]
        position = self._chooser.randint(0, len(data))
        data[position:position] = chunk

    def _splice(self, data: bytearray, donor: bytes) -> None:
        if not donor:
            return
        start = self._chooser.randrange(len(donor))
        chunk = donor[start : start + self._chooser.randint(1, MAX_CHUNK_BYTES)]
        position = self._chooser.randint(0, len(data))
        data[position : position + len(chunk)] = chunk

    def _truncate(self, data: bytearray, _donor: bytes) -> None:
        if data:
            del data[self._position(data) :]
