from kernel_protocol.errors.codes import (
    INVALID_HANDLE,
    IS_A_DIRECTORY,
    NOT_A_DIRECTORY,
    NOT_FOUND,
    KernelError,
)
from kernel_protocol.services.files import KIND_DIRECTORY, KIND_FILE, MODE_READ_ONLY
from kernel_services.filesystem.backends.base import Backend, Description
from kernel_services.filesystem.boot.layout import (
    FIRST_TABLE_BLOCK,
    Entry,
    blocks_for,
    check_compatibility,
    decode_header,
    decode_table,
)
from kernel_services.filesystem.format.codec import corrupted
from kernel_services.filesystem.format.names import SEPARATOR
from kernel_services.filesystem.storage import BlockStore

VERIFIED = "verified"


class BootNode:
    def __init__(self, kind: int) -> None:
        self.kind = kind
        self.children: dict[bytes, BootNode] = {}
        self.first_block = 0
        self.size = 0
        self.checksum = 0
        self.content: bytes | None = None
        self.references = 0


def as_node(value: object) -> BootNode:
    if not isinstance(value, BootNode):
        raise KernelError(INVALID_HANDLE, "node does not belong to the boot image")
    return value


def as_directory(value: object) -> BootNode:
    node = as_node(value)
    if node.kind != KIND_DIRECTORY:
        raise KernelError(NOT_A_DIRECTORY, "the node is not a directory")
    return node


def read_extent(store: BlockStore, first_block: int, size: int) -> bytes:
    blocks = [store.read(first_block + index) for index in range(blocks_for(size))]
    return b"".join(blocks)[:size]


def insert(root: BootNode, entry: Entry) -> None:
    names = entry.path.split(SEPARATOR)
    directory = root
    for name in names[:-1]:
        child = directory.children.get(name)
        if child is None:
            child = BootNode(KIND_DIRECTORY)
            directory.children[name] = child
        elif child.kind != KIND_DIRECTORY:
            raise corrupted("boot image path passes through a file")
        directory = child
    if names[-1] in directory.children:
        raise corrupted("boot image names a file and a directory alike")
    file = BootNode(KIND_FILE)
    file.first_block = entry.first_block
    file.size = entry.size
    file.checksum = entry.checksum
    directory.children[names[-1]] = file


class BootBackend(Backend):
    def __init__(self, store: BlockStore, runtime: bytes) -> None:
        header = decode_header(store.read(0), store)
        check_compatibility(header, runtime)
        next_block = FIRST_TABLE_BLOCK + blocks_for(header.table_bytes)
        if header.total_blocks > store.blocks or next_block > header.total_blocks:
            raise corrupted("boot image is larger than its device or smaller than its table")
        table = read_extent(store, FIRST_TABLE_BLOCK, header.table_bytes)
        if store.checksum(table) != header.table_checksum:
            raise corrupted("boot image table does not match its checksum")
        self._store = store
        self._total_blocks = header.total_blocks
        self._root = BootNode(KIND_DIRECTORY)
        for entry in decode_table(table, header.entries):
            if entry.first_block != next_block:
                raise corrupted("boot image files overlap or leave unowned blocks")
            next_block += blocks_for(entry.size)
            insert(self._root, entry)
        if next_block != header.total_blocks:
            raise corrupted("boot image declares blocks that no file owns")

    def root(self) -> object:
        return self._root

    def lookup(self, directory: object, name: bytes) -> object:
        child = as_directory(directory).children.get(name)
        if child is None:
            raise KernelError(NOT_FOUND, "directory has no entry with the name")
        return child

    def kind(self, node: object) -> int:
        return as_node(node).kind

    def size(self, node: object) -> int:
        return as_node(node).size

    def listing(self, directory: object) -> list[tuple[bytes, int, int]]:
        children = as_directory(directory).children
        return [(name, children[name].kind, children[name].size) for name in sorted(children)]

    def read(self, file: object, offset: int, count: int) -> bytes:
        node = as_node(file)
        if node.kind != KIND_FILE:
            raise KernelError(IS_A_DIRECTORY, "the node is not a file")
        content = node.content
        if content is None:
            content = read_extent(self._store, node.first_block, node.size)
            if self._store.checksum(content) != node.checksum:
                raise corrupted("boot file does not match the checksum of its entry")
            node.content = content
        return content[offset : offset + count]

    def describe(self) -> Description:
        return Description(MODE_READ_ONLY, VERIFIED, 0, 0, self._total_blocks)

    def close(self) -> None:
        self._store.close()

    def retain(self, node: object) -> None:
        as_node(node).references += 1

    def release(self, node: object) -> None:
        held = as_node(node)
        held.references -= 1
        if held.references == 0:
            held.content = None
