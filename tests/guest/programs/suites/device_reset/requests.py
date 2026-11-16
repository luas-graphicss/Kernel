from kernel_client import devices, memory
from suites.support.layout import PAGE_BYTES

HEADER_BYTES = 16
STATUS_OFFSET = 16
STATUS_BYTES = 1
DATA_OFFSET = 512
SECTOR_BYTES = 512
READ_FIRST_SECTOR = bytes(HEADER_BYTES)
STALLED_IDENTITY = b"kernel-stalled"
STALLED_SECTORS = 2048


def submit_read(device: int, buffer: int) -> int:
    mapping = memory.Mapping(buffer, True)
    mapping.write(0, READ_FIRST_SECTOR)
    mapping.unmap()
    return devices.submit(
        device,
        (
            (buffer, 0, HEADER_BYTES, False),
            (buffer, DATA_OFFSET, SECTOR_BYTES, True),
            (buffer, STATUS_OFFSET, STATUS_BYTES, True),
        ),
    )


def submit_headerless(device: int, buffer: int) -> int:
    return devices.submit(device, ((buffer, 0, PAGE_BYTES, True),))
