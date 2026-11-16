from runtime_selftest.checks import Checks

SMALL_LIMIT = 1 << 62
WORD = 1 << 64
FACTORIAL_OF_30 = 265252859812191058636308480000000


def factorial(count: int) -> int:
    product = 1
    for factor in range(2, count + 1):
        product *= factor
    return product


def run(checks: Checks) -> None:
    checks.require(SMALL_LIMIT - 1 + 1 == SMALL_LIMIT, "small integers promote without wrapping")
    checks.require((SMALL_LIMIT * 12) // 12 == SMALL_LIMIT, "long multiply and divide round-trip")
    checks.require(-7 // 2 == -4 and -7 % 2 == 1, "floor division follows the divisor sign")
    checks.require((-WORD) // 3 * 3 + (-WORD) % 3 == -WORD, "long floor division is consistent")
    checks.require((1 << 100) >> 100 == 1, "shifts beyond the word size are exact")
    checks.require(~WORD == -WORD - 1, "bitwise not works on long integers")
    checks.require(WORD ^ (WORD - 1) == 2 * WORD - 1, "bitwise xor works on long integers")
    checks.require((WORD - 1) & 0xFFFF == 0xFFFF, "bitwise and narrows a long integer")
    checks.require(abs(-WORD) == WORD, "abs works on long integers")
    checks.require(3**40 == 12157665459056928801, "power grows past the machine word")
    checks.require(factorial(30) == FACTORIAL_OF_30, "repeated multiplication stays exact")
    checks.require(str(WORD) == "18446744073709551616", "long integers convert to decimal")
    checks.require(int("1" + "0" * 30) == 10**30, "long decimal text parses")
    checks.require(
        (WORD + 5).to_bytes(9, "little") == b"\x05" + bytes(7) + b"\x01",
        "long integers serialize little-endian",
    )
    checks.require(
        int.from_bytes(b"\xff" * 9, "big") == (1 << 72) - 1, "long integers parse from bytes"
    )
    table = {WORD: "word", SMALL_LIMIT: "limit"}
    checks.require(
        table[1 << 64] == "word" and table[1 << 62] == "limit", "long integers hash by value"
    )
    checks.require(sorted([WORD, -WORD, 0, SMALL_LIMIT]) == [-WORD, 0, SMALL_LIMIT, WORD], "sort")
