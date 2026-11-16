from kernel_services.console.discipline import LineDiscipline
from kernel_services.console.service import write_text

MAX_LINE = 8
MAX_LINES = 2
ERASE = b"\x08 \x08"
BELL = b"\x07"


class Port:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.written = bytearray()

    def write(self, data: bytes, deadline: int) -> int:
        accepted = data[: self.capacity - len(self.written)]
        self.written.extend(accepted)
        return len(accepted)


def discipline() -> LineDiscipline:
    return LineDiscipline(MAX_LINE, MAX_LINES)


def test_typed_text_is_echoed_and_a_line_ends_at_return_or_line_feed() -> None:
    lines = discipline()

    assert lines.feed(b"ab\r") == b"ab\r\n"
    assert lines.feed(b"cd\n") == b"cd\r\n"
    assert lines.take_line() == b"ab"
    assert lines.take_line() == b"cd"
    assert lines.take_line() is None


def test_return_followed_by_line_feed_ends_one_line() -> None:
    lines = discipline()

    assert lines.feed(b"a\r\nb\r") == b"a\r\nb\r\n"
    assert lines.take_line() == b"a"
    assert lines.take_line() == b"b"
    lines.feed(b"\r")
    lines.feed(b"\n")
    assert lines.take_line() == b""
    assert lines.take_line() is None


def test_backspace_and_delete_erase_one_character_even_when_it_has_several_bytes() -> None:
    lines = discipline()

    assert lines.feed(b"a\xc3\xa7\x7f\x08\x08") == b"a\xc3\xa7" + ERASE + ERASE
    assert lines.feed(b"\xe2\x82\xac\x7fz\n") == b"\xe2\x82\xac" + ERASE + b"z\r\n"
    assert lines.take_line() == b"z"


def test_kill_erases_the_whole_line() -> None:
    lines = discipline()

    assert lines.feed(b"abc\x15") == b"abc" + ERASE * 3
    lines.feed(b"x\n")
    assert lines.take_line() == b"x"


def test_control_bytes_are_dropped_and_counted() -> None:
    lines = discipline()

    assert lines.feed(b"a\x00\x1b\x07b\n") == b"ab\r\n"
    assert lines.dropped_bytes == 3
    assert lines.take_line() == b"ab"


def test_line_longer_than_the_limit_rings_the_bell_and_keeps_the_start() -> None:
    lines = discipline()

    assert lines.feed(b"12345678") == b"12345678"
    assert lines.feed(b"9") == BELL
    lines.feed(b"\n")
    assert lines.dropped_bytes == 1
    assert lines.take_line() == b"12345678"


def test_lines_nobody_reads_are_bounded_and_the_excess_is_counted() -> None:
    lines = discipline()

    lines.feed(b"1\n2\n3\n")

    assert lines.dropped_lines == 1
    assert lines.take_line() == b"1"
    assert lines.take_line() == b"2"
    assert lines.take_line() is None


def test_output_turns_line_feed_into_return_and_line_feed() -> None:
    port = Port(64)

    assert write_text(port, b"one\ntwo\n", 0) == 8
    assert bytes(port.written) == b"one\r\ntwo\r\n"


def test_output_reports_how_much_a_slow_port_accepted() -> None:
    port = Port(6)

    assert write_text(port, b"one\ntwo\n", 0) == 5
    assert bytes(port.written) == b"one\r\nt"
