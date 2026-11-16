from kernel_protocol.errors.codes import (
    ALREADY_EXISTS,
    INVALID_ARGUMENT,
    IS_A_DIRECTORY,
    LIMIT_EXCEEDED,
    NOT_A_DIRECTORY,
    NOT_EMPTY,
    KernelError,
)
from kernel_services.filesystem.format.directory import Entry, entry_bytes
from kernel_services.filesystem.format.layout import (
    KIND_DIRECTORY,
    MAX_DEPTH,
    NO_BLOCK,
    PAYLOAD_BYTES,
)
from kernel_services.filesystem.format.names import check_name
from kernel_services.filesystem.transactions.nodes import DirectoryNode, FileNode, Node
from kernel_services.filesystem.transactions.state import (
    VolumeState,
    clean_ancestors,
    forget_dirty,
    mark_dirty,
    require_space,
)
from kernel_services.filesystem.transactions.tree import child, depth_of, height_of

DIRECTORY_FULL = "directory has no room for another entry"
TOO_DEEP = "directories would nest deeper than the format allows"


def attach(directory: DirectoryNode, name: bytes, entry: Entry, node: Node) -> None:
    directory.entries[name] = entry
    directory.loaded[name] = node
    directory.encoded_bytes += entry_bytes(name)
    node.parent = directory
    node.name = name


def detach(directory: DirectoryNode, name: bytes) -> None:
    del directory.entries[name]
    del directory.loaded[name]
    directory.encoded_bytes -= entry_bytes(name)


def discard(state: VolumeState, node: Node) -> None:
    if isinstance(node, FileNode):
        for block in node.map.allocated():
            state.allocator.release(block)
        node.map.resize(0)
    if node.block != NO_BLOCK:
        state.allocator.release(node.block)
        node.block = NO_BLOCK


def retire(state: VolumeState, node: Node) -> None:
    forget_dirty(state, node)
    node.removed = True
    node.parent = None
    if node.references == 0:
        discard(state, node)


def release(state: VolumeState, node: Node) -> None:
    node.references -= 1
    if node.removed and node.references == 0:
        discard(state, node)


def is_empty(node: Node) -> bool:
    return not isinstance(node, DirectoryNode) or len(node.entries) == 0


def is_inside(directory: DirectoryNode, ancestor: Node) -> bool:
    current: Node | None = directory
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def create(state: VolumeState, directory: DirectoryNode, name: bytes, kind: int) -> Node:
    check_name(name)
    if name in directory.entries:
        raise KernelError(ALREADY_EXISTS, "directory already has an entry with the name")
    if directory.encoded_bytes + entry_bytes(name) > PAYLOAD_BYTES:
        raise KernelError(LIMIT_EXCEEDED, DIRECTORY_FULL)
    if kind == KIND_DIRECTORY and depth_of(directory) == MAX_DEPTH:
        raise KernelError(LIMIT_EXCEEDED, TOO_DEEP)
    require_space(state, 0, clean_ancestors(directory) + 1, False)
    node: Node = DirectoryNode(state.next_node)
    if kind != KIND_DIRECTORY:
        node = FileNode(state.next_node)
    state.next_node += 1
    attach(directory, name, Entry(kind, node.identity, NO_BLOCK, 0, 0), node)
    mark_dirty(state, node)
    return node


def remove(state: VolumeState, directory: DirectoryNode, name: bytes) -> None:
    node = child(state, directory, name)
    if not is_empty(node):
        raise KernelError(NOT_EMPTY, "directory still has entries")
    require_space(state, 0, clean_ancestors(directory), True)
    mark_dirty(state, directory)
    detach(directory, name)
    retire(state, node)


def check_replacement(node: Node, replaced: Node) -> None:
    if replaced.kind != node.kind:
        if replaced.kind == KIND_DIRECTORY:
            raise KernelError(IS_A_DIRECTORY, "a file cannot replace a directory")
        raise KernelError(NOT_A_DIRECTORY, "a directory cannot replace a file")
    if not is_empty(replaced):
        raise KernelError(NOT_EMPTY, "the replaced directory still has entries")


def check_destination(
    state: VolumeState, node: Node, source: DirectoryNode, target: DirectoryNode, name: bytes
) -> None:
    freed = entry_bytes(node.name) if source is target else 0
    if isinstance(node, DirectoryNode):
        if is_inside(target, node):
            raise KernelError(INVALID_ARGUMENT, "a directory cannot move into itself")
        if depth_of(target) + height_of(state, node) > MAX_DEPTH:
            raise KernelError(LIMIT_EXCEEDED, TOO_DEEP)
    if name in target.entries:
        check_replacement(node, child(state, target, name))
    elif target.encoded_bytes - freed + entry_bytes(name) > PAYLOAD_BYTES:
        raise KernelError(LIMIT_EXCEEDED, DIRECTORY_FULL)


def rename(
    state: VolumeState,
    source: DirectoryNode,
    source_name: bytes,
    target: DirectoryNode,
    target_name: bytes,
) -> None:
    check_name(target_name)
    node = child(state, source, source_name)
    if source is target and source_name == target_name:
        return
    check_destination(state, node, source, target, target_name)
    replaces = target_name in target.entries
    require_space(state, 0, clean_ancestors(source) + clean_ancestors(target), replaces)
    mark_dirty(state, source)
    mark_dirty(state, target)
    if replaces:
        replaced = child(state, target, target_name)
        detach(target, target_name)
        retire(state, replaced)
    entry = source.entries[source_name]
    detach(source, source_name)
    attach(target, target_name, entry, node)


def listing(directory: DirectoryNode) -> list[tuple[bytes, int, int]]:
    listed = []
    for name in sorted(directory.entries):
        entry = directory.entries[name]
        node = directory.loaded.get(name)
        size = node.size if isinstance(node, FileNode) else entry.size
        listed.append((name, entry.kind, size))
    return listed
