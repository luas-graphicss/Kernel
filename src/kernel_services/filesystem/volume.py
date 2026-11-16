from kernel_protocol.errors.codes import (
    INVALID_ARGUMENT,
    IS_A_DIRECTORY,
    NO_SPACE,
    NOT_A_DIRECTORY,
    NOT_FOUND,
    KernelError,
)
from kernel_services.filesystem.allocation.allocator import Allocator
from kernel_services.filesystem.recovery.mount import Mounted, mount
from kernel_services.filesystem.storage import BlockStore
from kernel_services.filesystem.transactions import directories, files
from kernel_services.filesystem.transactions.commit import commit
from kernel_services.filesystem.transactions.nodes import DirectoryNode, FileNode, Node
from kernel_services.filesystem.transactions.state import VolumeState, check_usable, check_writable
from kernel_services.filesystem.transactions.tree import child, load_root

COMMITS_TO_RECLAIM = 2


def as_directory(node: Node) -> DirectoryNode:
    if node.removed:
        raise KernelError(NOT_FOUND, "the directory was removed")
    if not isinstance(node, DirectoryNode):
        raise KernelError(NOT_A_DIRECTORY, "the node is not a directory")
    return node


def as_file(node: Node) -> FileNode:
    if not isinstance(node, FileNode):
        raise KernelError(IS_A_DIRECTORY, "the node is not a file")
    return node


def as_living_file(node: Node) -> FileNode:
    if node.removed:
        raise KernelError(NOT_FOUND, "the file was removed")
    return as_file(node)


class Volume:
    def __init__(self, store: BlockStore, mounted: Mounted | None = None) -> None:
        self.mounted: Mounted = mount(store, False) if mounted is None else mounted
        survey = self.mounted.survey
        in_use = survey.reachable
        for block in self.mounted.retiring:
            in_use.set(block)
        free = survey.superblock.total_blocks - survey.used_blocks - len(self.mounted.retiring)
        allocator = Allocator(in_use, free, self.mounted.retiring)
        self._state = VolumeState(store, survey.superblock, allocator, self.mounted.read_only)
        load_root(self._state)

    def root(self) -> DirectoryNode:
        return self._state.root

    def is_read_only(self) -> bool:
        return self._state.read_only

    def has_failed(self) -> bool:
        return self._state.failed

    def generation(self) -> int:
        return self._state.superblock.generation

    def free_blocks(self) -> int:
        return self._state.allocator.free

    def total_blocks(self) -> int:
        return self._state.superblock.total_blocks

    def has_pending_changes(self) -> bool:
        return self._state.root.dirty

    def checksum(self, data: bytes, seed: int = 0) -> int:
        return self._state.store.checksum(data, seed)

    def lookup(self, directory: Node, name: bytes) -> Node:
        check_usable(self._state)
        return child(self._state, as_directory(directory), name)

    def listing(self, directory: Node) -> list[tuple[bytes, int, int]]:
        check_usable(self._state)
        return directories.listing(as_directory(directory))

    def create(self, directory: Node, name: bytes, kind: int) -> Node:
        check_writable(self._state)
        parent = as_directory(directory)
        try:
            return directories.create(self._state, parent, name, kind)
        except KernelError as error:
            self._reclaim(error)
        return directories.create(self._state, parent, name, kind)

    def remove(self, directory: Node, name: bytes) -> None:
        check_writable(self._state)
        directories.remove(self._state, as_directory(directory), name)

    def rename(self, source: Node, source_name: bytes, target: Node, target_name: bytes) -> None:
        check_writable(self._state)
        directories.rename(
            self._state, as_directory(source), source_name, as_directory(target), target_name
        )

    def read(self, file: Node, offset: int, count: int) -> bytes:
        check_usable(self._state)
        if offset < 0 or count < 0:
            raise KernelError(INVALID_ARGUMENT, "offset and count cannot be negative")
        return files.read(self._state, as_file(file), offset, count)

    def write(self, file: Node, offset: int, data: bytes) -> int:
        check_writable(self._state)
        target = as_living_file(file)
        if offset < 0:
            raise KernelError(INVALID_ARGUMENT, "offset cannot be negative")
        written = self._write_available(target, offset, data)
        if written < len(data) and self._state.allocator.reclaimable() != 0:
            self._commit_to_reclaim()
            written += self._write_available(target, offset + written, data[written:])
        if written == 0 and len(data) != 0:
            raise KernelError(NO_SPACE, "the volume has no room left for the data")
        return written

    def truncate(self, file: Node, size: int) -> None:
        check_writable(self._state)
        target = as_living_file(file)
        if size < 0:
            raise KernelError(INVALID_ARGUMENT, "size cannot be negative")
        try:
            files.truncate(self._state, target, size)
            return
        except KernelError as error:
            self._reclaim(error)
        files.truncate(self._state, target, size)

    def sync(self) -> None:
        check_writable(self._state)
        commit(self._state, False)

    def retain(self, node: Node) -> None:
        node.references += 1

    def release(self, node: Node) -> None:
        directories.release(self._state, node)

    def _write_available(self, file: FileNode, offset: int, data: bytes) -> int:
        try:
            return files.write(self._state, file, offset, data)
        except KernelError as error:
            if error.code != NO_SPACE:
                raise
        return 0

    def _commit_to_reclaim(self) -> None:
        for _commit in range(COMMITS_TO_RECLAIM):
            commit(self._state, True)

    def _reclaim(self, error: KernelError) -> None:
        if error.code != NO_SPACE or self._state.allocator.reclaimable() == 0:
            raise error
        self._commit_to_reclaim()
