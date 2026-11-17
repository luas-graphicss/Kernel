ESCAPE = 0x1B
CONTROL_SEQUENCE_INTRODUCER = 0x5B
SINGLE_SHIFT_THREE = 0x4F
FIRST_PRINTABLE = 0x20
LAST_INTERMEDIATE = 0x2F
LAST_PARAMETER = 0x3F
DELETE = 0x7F

OUTSIDE = 0
AFTER_ESCAPE = 1
IN_CONTROL_SEQUENCE = 2
AFTER_SINGLE_SHIFT = 3


class EscapeSequences:
    def __init__(self) -> None:
        self._state = OUTSIDE

    def swallows(self, value: int) -> bool:
        if value == ESCAPE:
            self._state = AFTER_ESCAPE
            return True
        state = self._state
        if state == OUTSIDE:
            return False
        if value < FIRST_PRINTABLE or value == DELETE:
            self._state = OUTSIDE
            return False
        if state == AFTER_ESCAPE:
            self._state = _after_escape(value)
        elif state == AFTER_SINGLE_SHIFT or value > LAST_PARAMETER:
            self._state = OUTSIDE
        return True


def _after_escape(value: int) -> int:
    if value == CONTROL_SEQUENCE_INTRODUCER:
        return IN_CONTROL_SEQUENCE
    if value == SINGLE_SHIFT_THREE:
        return AFTER_SINGLE_SHIFT
    if value <= LAST_INTERMEDIATE:
        return AFTER_ESCAPE
    return OUTSIDE
