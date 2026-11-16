from kernel_protocol.errors.codes import INVALID_ARGUMENT, KernelError
from kernel_services.filesystem.format.layout import MAX_NAME_BYTES

SEPARATOR = b"/"
CURRENT = b"."
PARENT = b".."
NUL = b"\x00"
CONTINUATION_LOW = 0x80
CONTINUATION_HIGH = 0xBF
ASCII_LIMIT = 0x80


def sequence_shape(lead: int) -> tuple[int, int, int]:
    if 0xC2 <= lead <= 0xDF:
        return 1, CONTINUATION_LOW, CONTINUATION_HIGH
    if lead == 0xE0:
        return 2, 0xA0, CONTINUATION_HIGH
    if lead == 0xED:
        return 2, CONTINUATION_LOW, 0x9F
    if 0xE1 <= lead <= 0xEF:
        return 2, CONTINUATION_LOW, CONTINUATION_HIGH
    if lead == 0xF0:
        return 3, 0x90, CONTINUATION_HIGH
    if lead == 0xF4:
        return 3, CONTINUATION_LOW, 0x8F
    if 0xF1 <= lead <= 0xF3:
        return 3, CONTINUATION_LOW, CONTINUATION_HIGH
    return 0, 0, 0


def is_utf8(text: bytes) -> bool:
    index = 0
    while index < len(text):
        lead = text[index]
        index += 1
        if lead < ASCII_LIMIT:
            continue
        continuations, low, high = sequence_shape(lead)
        if continuations == 0 or index + continuations > len(text):
            return False
        if text[index] < low or text[index] > high:
            return False
        for position in range(index + 1, index + continuations):
            if text[position] < CONTINUATION_LOW or text[position] > CONTINUATION_HIGH:
                return False
        index += continuations
    return True


def name_is_valid(name: bytes) -> bool:
    if len(name) == 0 or len(name) > MAX_NAME_BYTES or name in (CURRENT, PARENT):
        return False
    return SEPARATOR not in name and NUL not in name and is_utf8(name)


def check_name(name: bytes) -> None:
    if not name_is_valid(name):
        raise KernelError(INVALID_ARGUMENT, "name is empty, too long, reserved or not UTF-8")
