from kernel_protocol.errors.codes import NOT_FOUND, KernelError
from kernel_services.filesystem.format.blocks import decode_block
from kernel_services.filesystem.format.codec import corrupted
from kernel_services.filesystem.format.directory import Entry, decode_entries
from kernel_services.filesystem.format.index import blocks_for, decode_index
from kernel_services.filesystem.format.layout import (
    DIRECTORY_MAGIC,
    INDEX_MAGIC,
    KIND_DIRECTORY,
    NO_BLOCK,
)
from kernel_services.filesystem.storage import read_verified
from kernel_services.filesystem.transactions.nodes import DirectoryNode, FileNode, Node
from kernel_services.filesystem.transactions.state import VolumeState


def read_metadata(state: VolumeState, block: int, checksum: int, magic: bytes) -> bytes:
    data = read_verified(state.store, block, checksum)
    return decode_block(data, magic, state.superblock.generation)[1]


def fill_directory(state: VolumeState, node: DirectoryNode, block: int, checksum: int) -> None:
    payload = read_metadata(state, block, checksum, DIRECTORY_MAGIC)
    node.entries = decode_entries(payload)
    node.encoded_bytes = len(payload)
    node.block = block
    node.checksum = checksum


def load_root(state: VolumeState) -> None:
    fill_directory(state, state.root, state.superblock.root_block, state.superblock.root_checksum)


def load_file(state: VolumeState, entry: Entry) -> FileNode:
    node = FileNode(entry.node)
    node.size = entry.size
    node.block = entry.block
    node.checksum = entry.checksum
    if entry.block != NO_BLOCK:
        payload = read_metadata(state, entry.block, entry.checksum, INDEX_MAGIC)
        node.map = decode_index(payload, blocks_for(entry.size))
    elif entry.size != 0:
        raise corrupted("file with a size has no index block")
    return node


def child(state: VolumeState, directory: DirectoryNode, name: bytes) -> Node:
    node = directory.loaded.get(name)
    if node is not None:
        return node
    entry = directory.entries.get(name)
    if entry is None:
        raise KernelError(NOT_FOUND, "directory has no entry with the name")
    if entry.kind == KIND_DIRECTORY:
        loaded = DirectoryNode(entry.node)
        fill_directory(state, loaded, entry.block, entry.checksum)
        node = loaded
    else:
        node = load_file(state, entry)
    node.parent = directory
    node.name = name
    directory.loaded[name] = node
    return node


def depth_of(node: Node) -> int:
    depth = 0
    current: Node | None = node
    while current is not None:
        depth += 1
        current = current.parent
    return depth


def height_of(state: VolumeState, node: Node) -> int:
    tallest = 1
    pending: list[tuple[Node, int]] = [(node, 1)]
    while pending:
        current, level = pending.pop()
        if level > tallest:
            tallest = level
        if isinstance(current, DirectoryNode):
            for name in current.entries:
                if current.entries[name].kind == KIND_DIRECTORY:
                    pending.append((child(state, current, name), level + 1))
    return tallest
