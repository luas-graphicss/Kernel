import _probe

from kernel_client import memory
from kernel_protocol.identity.rights import RIGHT_READ
from suites.support import raw
from suites.support.layout import Layout

BUFFER_BYTES = 0x100000
HEAP_TAIL_BYTES = 0x10000
STACK_FLOOR_BYTES = 0x4000


def main() -> bool:
    layout = Layout()
    status, address, length = raw.map_buffer(memory.create_buffer(BUFFER_BYTES), RIGHT_READ)
    if status != 0:
        return False
    regions = (
        ("buffer", address, length),
        ("heap", layout.heap_end - HEAP_TAIL_BYTES, HEAP_TAIL_BYTES),
        ("stack", layout.stack_bottom, STACK_FLOOR_BYTES),
    )
    clean = True
    for name, start, size in regions:
        dirty = _probe.count_nonzero(start, size)
        if dirty != 0:
            print(f"inspector: region={name} dirty-bytes={dirty}")
            clean = False
    return clean
