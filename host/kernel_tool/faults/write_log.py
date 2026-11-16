import struct

from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_tool.faults.device_log import DeviceEvent, DeviceFlush, DeviceWrite
from kernel_tool.outcome import CheckError

MAGIC = 0x6A736677736872
VERSION = 1
HEADER = struct.Struct("<QQQI")
ENTRY = struct.Struct("<QQQQ")
FLAG_FLUSH = 0x1


def read_write_log(content: bytes) -> list[DeviceEvent]:
    if len(content) < HEADER.size:
        raise CheckError("the write log is shorter than its header")
    magic, version, entries, sector_bytes = HEADER.unpack_from(content)
    if magic != MAGIC or version != VERSION:
        raise CheckError(f"the write log has magic {magic:#x} and version {version}")
    if sector_bytes == 0 or BLOCK_BYTES % sector_bytes:
        raise CheckError(f"the write log uses sectors of {sector_bytes} bytes")

    events: list[DeviceEvent] = []
    offset = sector_bytes
    for _ in range(entries):
        if offset + ENTRY.size > len(content):
            raise CheckError("the write log ends inside an entry")
        sector, sectors, flags, _data_bytes = ENTRY.unpack_from(content, offset)
        offset += sector_bytes
        if flags & ~FLAG_FLUSH:
            raise CheckError(f"the write log has an entry with unknown flags {flags:#x}")
        data = content[offset : offset + sectors * sector_bytes]
        if len(data) != sectors * sector_bytes:
            raise CheckError("the write log ends inside the data of an entry")
        offset += len(data)
        events.extend(_block_writes(sector * sector_bytes, data))
        if flags & FLAG_FLUSH:
            events.append(DeviceFlush())
    return events


def _block_writes(start: int, data: bytes) -> list[DeviceWrite]:
    if start % BLOCK_BYTES or len(data) % BLOCK_BYTES:
        raise CheckError(f"the write at byte {start} is not made of whole blocks")
    return [
        DeviceWrite((start + position) // BLOCK_BYTES, data[position : position + BLOCK_BYTES])
        for position in range(0, len(data), BLOCK_BYTES)
    ]
