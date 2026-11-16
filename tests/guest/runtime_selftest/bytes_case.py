from runtime_selftest.checks import Checks


def run(checks: Checks) -> None:
    data = bytes(range(16))
    checks.require(data[4:8] == b"\x04\x05\x06\x07", "bytes slice by range")
    checks.require(data[-2:] == b"\x0e\x0f", "bytes slice from the end")
    checks.require(sum(data) == 120 and len(data) == 16, "bytes iterate as integers")
    checks.require(bytes(4) == b"\x00\x00\x00\x00", "bytes of a length are zeroed")
    checks.require(list(b"\x01\x02") == [1, 2], "bytes convert to a list")
    checks.require(b"".join([b"ab", b"cd", b"ef"]) == b"abcdef", "bytes join")
    checks.require(b"cd" in b"abcdef" and b"x" not in b"abcdef", "bytes containment")
    checks.require(b"abc" < b"abd" and b"abc" != b"abC", "bytes compare lexicographically")

    buffer = bytearray(data)
    buffer[0] = 0xFF
    buffer.extend(b"\x10\x11")
    checks.require(len(buffer) == 18 and buffer[0] == 0xFF, "bytearray is mutable and grows")
    checks.require(data[0] == 0, "a bytearray copy does not alias the source bytes")
    checks.require(bytes(buffer[16:]) == b"\x10\x11", "bytearray slices convert to bytes")
    checks.require(buffer[1:3] == bytearray(b"\x01\x02"), "bytearray slices compare by content")
    buffer.append(0x12)
    checks.require(buffer[-1] == 0x12 and len(buffer) == 19, "bytearray appends one byte")
