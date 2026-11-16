WRITERS = 3
RECORDS = 8
RECORD_BYTES = 64
FIRST_LETTER = 65
FIRST_DIGIT = 48


def record_of(slot: int, record: int) -> bytes:
    return bytes([FIRST_LETTER + slot]) * (RECORD_BYTES - 1) + bytes([FIRST_DIGIT + record])
