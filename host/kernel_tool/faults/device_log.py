from collections.abc import Callable
from dataclasses import dataclass

from kernel_services.filesystem.format.codec import get
from kernel_services.filesystem.format.layout import (
    SUPERBLOCK_GENERATION,
    SUPERBLOCK_MAGIC,
    SUPERBLOCK_SLOTS,
)
from kernel_tool.storage.image_store import ImageStore

GENERATION_BYTES = 8


@dataclass(frozen=True, slots=True)
class DeviceWrite:
    block: int
    data: bytes


@dataclass(frozen=True, slots=True)
class DeviceFlush:
    pass


type DeviceEvent = DeviceWrite | DeviceFlush


def published_generation(event: DeviceEvent) -> int | None:
    if isinstance(event, DeviceFlush) or event.block >= SUPERBLOCK_SLOTS:
        return None
    if event.data[: len(SUPERBLOCK_MAGIC)] != SUPERBLOCK_MAGIC:
        return None
    return get(event.data, SUPERBLOCK_GENERATION, GENERATION_BYTES)


def describe(event: DeviceEvent) -> str:
    if isinstance(event, DeviceFlush):
        return "flush"
    generation = published_generation(event)
    if generation is not None:
        return f"superblock of generation {generation}"
    return f"write of block {event.block}"


class RecordingStore(ImageStore):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.events: list[DeviceEvent] = []
        self.on_publish: Callable[[int], None] | None = None

    def write(self, block: int, data: bytes) -> None:
        super().write(block, data)
        event = DeviceWrite(block, bytes(data))
        self.events.append(event)
        generation = published_generation(event)
        if generation is not None and self.on_publish is not None:
            self.on_publish(generation)

    def flush(self) -> None:
        self.events.append(DeviceFlush())
