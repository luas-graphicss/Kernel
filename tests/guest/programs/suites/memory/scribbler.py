from kernel_client import memory
from suites.memory.inspector import BUFFER_BYTES
from suites.support.layout import PAGE_BYTES

FILL = b"\xa5" * PAGE_BYTES


def fill_buffer() -> None:
    mapping = memory.Mapping(memory.create_buffer(BUFFER_BYTES), True)
    for offset in range(0, mapping.size, PAGE_BYTES):
        mapping.write(offset, FILL)


def fill_heap() -> int:
    blocks = []
    try:
        while True:
            blocks.append(bytearray(FILL))
    except MemoryError:
        return len(blocks)


def descend(depth: int) -> int:
    return descend(depth + 1)


def fill_stack() -> bool:
    try:
        descend(0)
    except RuntimeError:
        return True
    return False


def main() -> bool:
    fill_buffer()
    return fill_stack() and fill_heap() > 0
