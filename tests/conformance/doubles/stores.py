from kernel_protocol.errors.codes import IO_ERROR, KernelError
from kernel_services.filesystem.creation import create_volume
from kernel_services.filesystem.format.layout import BLOCK_BYTES
from kernel_services.filesystem.volume import Volume
from kernel_tool.storage.image_store import ImageStore

VOLUME = 0x54455354


class FailingStore(ImageStore):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.failing_write: int | None = None
        self.failing_flush: int | None = None
        self.writes = 0
        self.flushes = 0

    def write(self, block: int, data: bytes) -> None:
        self.writes += 1
        if self.writes == self.failing_write:
            raise KernelError(IO_ERROR, "injected write failure")
        super().write(block, data)

    def flush(self) -> None:
        self.flushes += 1
        if self.flushes == self.failing_flush:
            raise KernelError(IO_ERROR, "injected flush failure")


def formatted(blocks: int) -> bytes:
    store = ImageStore(bytes(blocks * BLOCK_BYTES))
    create_volume(store, VOLUME)
    return bytes(store.content)


def fresh_volume(blocks: int = 64) -> tuple[ImageStore, Volume]:
    store = ImageStore(formatted(blocks))
    return store, Volume(store)


def remounted(store: ImageStore) -> Volume:
    return Volume(ImageStore(bytes(store.content)))
