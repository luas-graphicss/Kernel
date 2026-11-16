from kernel_protocol.errors.codes import IO_ERROR, UNKNOWN_OUTCOME, KernelError
from kernel_services.filesystem.format.blocks import encode_block
from kernel_services.filesystem.format.directory import encode_entries
from kernel_services.filesystem.format.index import encode_index
from kernel_services.filesystem.format.layout import DIRECTORY_MAGIC, INDEX_MAGIC, NO_BLOCK
from kernel_services.filesystem.format.superblock import Superblock, encode_superblock, slot_of
from kernel_services.filesystem.transactions.nodes import DirectoryNode, FileNode, Node
from kernel_services.filesystem.transactions.state import VolumeState, mark_dirty

NOT_REACHED = "the commit did not reach the device"
UNCERTAIN = "the commit may or may not have reached the device"


def dirty_directories(root: DirectoryNode) -> list[DirectoryNode]:
    found = []
    pending = [root]
    while pending:
        directory = pending.pop()
        found.append(directory)
        for name in directory.loaded:
            node = directory.loaded[name]
            if node.dirty and isinstance(node, DirectoryNode):
                pending.append(node)
    return found


def relocate(state: VolumeState, node: Node, content: bytes) -> None:
    target = state.allocator.allocate()
    state.store.write(target, content)
    if node.block != NO_BLOCK:
        state.allocator.release(node.block)
    node.block = target
    node.checksum = state.store.checksum(content)


def record(node: Node) -> None:
    node.dirty = False
    if node.parent is not None:
        entry = node.parent.entries[node.name]
        entry.block = node.block
        entry.checksum = node.checksum
        if isinstance(node, FileNode):
            entry.size = node.size


def write_file(state: VolumeState, file: FileNode, generation: int) -> None:
    if len(file.map.blocks) != 0:
        relocate(state, file, encode_block(INDEX_MAGIC, generation, encode_index(file.map)))
    elif file.block != NO_BLOCK:
        state.allocator.release(file.block)
        file.block = NO_BLOCK
        file.checksum = 0
    record(file)


def write_directory(state: VolumeState, directory: DirectoryNode, generation: int) -> None:
    for name in directory.loaded:
        node = directory.loaded[name]
        if node.dirty and isinstance(node, FileNode):
            write_file(state, node, generation)
    payload = encode_entries(directory.entries)
    relocate(state, directory, encode_block(DIRECTORY_MAGIC, generation, payload))
    record(directory)


def write_tree(state: VolumeState, generation: int) -> None:
    directories = dirty_directories(state.root)
    position = len(directories)
    while position > 0:
        position -= 1
        write_directory(state, directories[position], generation)
    state.store.flush()


def staged(state: VolumeState, generation: int) -> bool:
    try:
        write_tree(state, generation)
    except KernelError:
        return False
    return True


def published(state: VolumeState, superblock: Superblock) -> bool:
    try:
        state.store.write(
            slot_of(superblock.generation), encode_superblock(superblock, state.store)
        )
        state.store.flush()
    except KernelError:
        return False
    return True


def commit(state: VolumeState, force: bool) -> None:
    if force:
        mark_dirty(state, state.root)
    if not state.root.dirty:
        return
    generation = state.superblock.generation + 1
    if not staged(state, generation):
        state.failed = True
        raise KernelError(IO_ERROR, NOT_REACHED)
    superblock = Superblock(
        generation=generation,
        total_blocks=state.superblock.total_blocks,
        next_node=state.next_node,
        root_block=state.root.block,
        root_checksum=state.root.checksum,
        volume=state.superblock.volume,
    )
    if not published(state, superblock):
        state.failed = True
        raise KernelError(UNKNOWN_OUTCOME, UNCERTAIN)
    state.superblock = superblock
    state.allocator.publish()
    state.pending_metadata = 0
