import _probe

PAGE_BYTES = 4096
WORD_BYTES = 8
NULL_PAGE = 0
CONSOLE_REGISTERS = 0x10000000
BUFFER_WINDOW = 0x50000000
SUPERVISOR_IMAGE = 0x80200000
SUPERVISOR_MEMORY = 0x8F000000


class Layout:
    def __init__(self) -> None:
        (
            self.heap_start,
            self.heap_end,
            self.stack_bottom,
            self.stack_top,
            self.text,
            self.read_only,
        ) = _probe.layout()

    def above_stack(self) -> int:
        return (self.stack_top | (PAGE_BYTES - 1)) + 1
