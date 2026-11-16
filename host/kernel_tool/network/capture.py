import struct
import time
from pathlib import Path
from typing import BinaryIO

MAGIC = 0xA1B2C3D4
VERSION_MAJOR = 2
VERSION_MINOR = 4
LINK_TYPE_ETHERNET = 1
MICROSECONDS = 1_000_000
GLOBAL_HEADER = struct.Struct("<IHHiIII")
RECORD_HEADER = struct.Struct("<IIII")


class Capture:
    def __init__(self, path: Path, snap_bytes: int) -> None:
        self._snap_bytes = snap_bytes
        self._started = time.monotonic()
        self._file: BinaryIO = path.open("wb")
        self._file.write(
            GLOBAL_HEADER.pack(
                MAGIC, VERSION_MAJOR, VERSION_MINOR, 0, 0, snap_bytes, LINK_TYPE_ETHERNET
            )
        )
        self.frames = 0

    def record(self, frame: bytes) -> None:
        elapsed = time.monotonic() - self._started
        seconds = int(elapsed)
        microseconds = int((elapsed - seconds) * MICROSECONDS)
        kept = frame[: self._snap_bytes]
        self._file.write(RECORD_HEADER.pack(seconds, microseconds, len(kept), len(frame)))
        self._file.write(kept)
        self.frames += 1

    def close(self) -> None:
        self._file.close()


def read_capture(path: Path) -> list[tuple[int, bytes]]:
    content = path.read_bytes()
    magic, _major, _minor, _zone, _accuracy, _snap, link_type = GLOBAL_HEADER.unpack_from(content)
    if magic != MAGIC or link_type != LINK_TYPE_ETHERNET:
        raise ValueError(f"{path} is not an Ethernet capture")
    records = []
    position = GLOBAL_HEADER.size
    while position < len(content):
        _seconds, _microseconds, kept, original = RECORD_HEADER.unpack_from(content, position)
        position += RECORD_HEADER.size
        records.append((original, content[position : position + kept]))
        position += kept
    return records
