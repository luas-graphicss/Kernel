from kernel_protocol.errors.codes import INVALID_HANDLE, KernelError
from kernel_protocol.services.files import MODE_READ_ONLY, MODE_READ_WRITE
from kernel_services.filesystem.backends.base import Backend, Description
from kernel_services.filesystem.storage import BlockStore
from kernel_services.filesystem.transactions.nodes import FileNode, Node
from kernel_services.filesystem.volume import Volume

FAILED = "failed"


def as_node(value: object) -> Node:
    if not isinstance(value, Node):
        raise KernelError(INVALID_HANDLE, "node does not belong to the volume")
    return value


class VolumeBackend(Backend):
    def __init__(self, store: BlockStore) -> None:
        self._store = store
        self._volume = Volume(store)

    def close(self) -> None:
        self._store.close()

    def root(self) -> object:
        return self._volume.root()

    def lookup(self, directory: object, name: bytes) -> object:
        return self._volume.lookup(as_node(directory), name)

    def kind(self, node: object) -> int:
        return as_node(node).kind

    def size(self, node: object) -> int:
        return node.size if isinstance(node, FileNode) else 0

    def listing(self, directory: object) -> list[tuple[bytes, int, int]]:
        return self._volume.listing(as_node(directory))

    def read(self, file: object, offset: int, count: int) -> bytes:
        return self._volume.read(as_node(file), offset, count)

    def describe(self) -> Description:
        volume = self._volume
        mode = MODE_READ_ONLY if volume.is_read_only() else MODE_READ_WRITE
        reason = FAILED if volume.has_failed() else volume.mounted.reason
        return Description(
            mode, reason, volume.generation(), volume.free_blocks(), volume.total_blocks()
        )

    def create(self, directory: object, name: bytes, kind: int) -> object:
        return self._volume.create(as_node(directory), name, kind)

    def remove(self, directory: object, name: bytes) -> None:
        self._volume.remove(as_node(directory), name)

    def rename(
        self, source: object, source_name: bytes, target: object, target_name: bytes
    ) -> None:
        self._volume.rename(as_node(source), source_name, as_node(target), target_name)

    def write(self, file: object, offset: int, data: bytes) -> int:
        return self._volume.write(as_node(file), offset, data)

    def truncate(self, file: object, size: int) -> None:
        self._volume.truncate(as_node(file), size)

    def sync(self) -> None:
        if not self._volume.is_read_only():
            self._volume.sync()

    def retain(self, node: object) -> None:
        self._volume.retain(as_node(node))

    def release(self, node: object) -> None:
        self._volume.release(as_node(node))
