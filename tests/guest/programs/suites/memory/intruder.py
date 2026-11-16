import _probe

from kernel_client.processes import Startup
from suites.support.layout import (
    BUFFER_WINDOW,
    CONSOLE_REGISTERS,
    NULL_PAGE,
    SUPERVISOR_IMAGE,
    SUPERVISOR_MEMORY,
    WORD_BYTES,
    Layout,
)


def store_zero(address: int) -> None:
    _probe.store(address, 0)


OPERATIONS = {"load": _probe.load, "store": store_zero, "jump": _probe.jump}


def target_address(name: str) -> int:
    layout = Layout()
    targets = {
        "null": NULL_PAGE,
        "supervisor-image": SUPERVISOR_IMAGE,
        "supervisor-memory": SUPERVISOR_MEMORY,
        "console": CONSOLE_REGISTERS,
        "guard": layout.stack_bottom - WORD_BYTES,
        "above-stack": layout.above_stack(),
        "buffer-window": BUFFER_WINDOW,
        "text": layout.text,
        "read-only": layout.read_only,
        "heap": layout.heap_start,
        "stack": layout.stack_bottom,
    }
    return targets[name]


def main() -> bool:
    operation, target = str(Startup().argument, "ascii").split(" ")
    OPERATIONS[operation](target_address(target))
    return True
