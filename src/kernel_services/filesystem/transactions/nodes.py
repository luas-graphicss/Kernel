from kernel_services.filesystem.format.directory import Entry
from kernel_services.filesystem.format.index import BlockMap
from kernel_services.filesystem.format.layout import KIND_DIRECTORY, KIND_FILE, NO_BLOCK


class Node:
    def __init__(self, identity: int, kind: int) -> None:
        self.identity = identity
        self.kind = kind
        self.parent: DirectoryNode | None = None
        self.name = b""
        self.block = NO_BLOCK
        self.checksum = 0
        self.dirty = False
        self.removed = False
        self.references = 0


class FileNode(Node):
    def __init__(self, identity: int) -> None:
        super().__init__(identity, KIND_FILE)
        self.size = 0
        self.map = BlockMap()


class DirectoryNode(Node):
    def __init__(self, identity: int) -> None:
        super().__init__(identity, KIND_DIRECTORY)
        self.entries: dict[bytes, Entry] = {}
        self.loaded: dict[bytes, Node] = {}
        self.encoded_bytes = 0
