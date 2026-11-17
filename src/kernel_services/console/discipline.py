from kernel_services.console.escapes import EscapeSequences

LINE_FEED = 0x0A
CARRIAGE_RETURN = 0x0D
BACKSPACE = 0x08
TAB = 0x09
DELETE = 0x7F
KILL_LINE = 0x15
SPACE = 0x20
FIRST_PRINTABLE = 0x20
CONTINUATION_MASK = 0xC0
CONTINUATION_BITS = 0x80

BELL = b"\x07"
ERASE = b"\x08 \x08"
NEW_LINE = b"\r\n"
LINE_FEED_BYTES = b"\n"
DROPPED_LINES_NOTICE = "console: dropped-lines="


class OverlongLine:
    pass


OVERLONG_LINE = OverlongLine()


class LineDiscipline:
    def __init__(self, max_line_bytes: int, max_lines: int) -> None:
        self._max_line_bytes = max_line_bytes
        self._max_lines = max_lines
        self._line = bytearray()
        self._is_overlong = False
        self._lines: list[bytes | OverlongLine] = []
        self._after_return = False
        self._escapes = EscapeSequences()
        self.dropped_bytes = 0
        self.dropped_lines = 0

    def feed(self, data: bytes) -> bytes:
        echo = bytearray()
        for value in data:
            self._accept(value, echo)
        return bytes(echo)

    def take_line(self) -> bytes | OverlongLine | None:
        if not self._lines:
            return None
        return self._lines.pop(0)

    def _accept(self, value: int, echo: bytearray) -> None:
        if self._escapes.swallows(value):
            self.dropped_bytes += 1
            return
        follows_return = self._after_return
        self._after_return = value == CARRIAGE_RETURN
        if value == LINE_FEED and follows_return:
            return
        if value in (CARRIAGE_RETURN, LINE_FEED):
            self._finish(echo)
        elif value in (BACKSPACE, DELETE):
            self._erase(echo)
        elif value == KILL_LINE:
            while len(self._line) != 0:
                self._erase(echo)
        elif value == TAB:
            self._type(SPACE, echo)
        elif value < FIRST_PRINTABLE:
            self.dropped_bytes += 1
        else:
            self._type(value, echo)

    def _type(self, value: int, echo: bytearray) -> None:
        if len(self._line) == self._max_line_bytes:
            self.dropped_bytes += 1
            self._is_overlong = True
            echo.extend(BELL)
            return
        self._line.append(value)
        echo.append(value)

    def _finish(self, echo: bytearray) -> None:
        echo.extend(NEW_LINE)
        if len(self._lines) == self._max_lines:
            self.dropped_lines += 1
            echo.extend(bytes(f"{DROPPED_LINES_NOTICE}{self.dropped_lines}", "utf-8"))
            echo.extend(NEW_LINE)
        elif self._is_overlong:
            self._lines.append(OVERLONG_LINE)
        else:
            self._lines.append(bytes(self._line))
        self._line = bytearray()
        self._is_overlong = False

    def _erase(self, echo: bytearray) -> None:
        end = len(self._line)
        if end == 0:
            return
        end -= 1
        while end > 0 and self._line[end] & CONTINUATION_MASK == CONTINUATION_BITS:
            end -= 1
        self._line = self._line[:end]
        if end == 0:
            self._is_overlong = False
        echo.extend(ERASE)
