SPACE = 1 << 32
MASK = SPACE - 1
HALF = 1 << 31


def advance(sequence: int, amount: int) -> int:
    return (sequence + amount) & MASK


def distance(later: int, earlier: int) -> int:
    return (later - earlier) & MASK


def is_before(first: int, second: int) -> bool:
    return first != second and distance(second, first) < HALF


def is_at_or_before(first: int, second: int) -> bool:
    return distance(second, first) < HALF
