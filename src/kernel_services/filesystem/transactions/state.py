from kernel_protocol.errors.codes import IO_ERROR, NO_SPACE, READ_ONLY, KernelError
from kernel_services.filesystem.allocation.allocator import Allocator
from kernel_services.filesystem.format.codec import smaller
from kernel_services.filesystem.format.layout import ROOT_NODE
from kernel_services.filesystem.format.superblock import Superblock
from kernel_services.filesystem.storage import BlockStore
from kernel_services.filesystem.transactions.nodes import DirectoryNode, Node

MAX_RESERVE_BLOCKS = 34
RESERVE_FRACTION = 8


class VolumeState:
    def __init__(
        self, store: BlockStore, superblock: Superblock, allocator: Allocator, read_only: bool
    ) -> None:
        self.store = store
        self.superblock = superblock
        self.allocator = allocator
        self.read_only = read_only
        self.failed = False
        self.next_node = superblock.next_node
        self.pending_metadata = 0
        self.reserve = smaller(MAX_RESERVE_BLOCKS, superblock.total_blocks // RESERVE_FRACTION)
        self.root = DirectoryNode(ROOT_NODE)


def check_usable(state: VolumeState) -> None:
    if state.failed:
        raise KernelError(IO_ERROR, "the volume failed and must be mounted again")


def check_writable(state: VolumeState) -> None:
    check_usable(state)
    if state.read_only:
        raise KernelError(READ_ONLY, "the volume is mounted read-only")


def clean_ancestors(node: Node) -> int:
    clean = 0
    current: Node | None = node
    while current is not None and not current.dirty:
        clean += 1
        current = current.parent
    return clean


def mark_dirty(state: VolumeState, node: Node) -> None:
    current: Node | None = node
    while current is not None and not current.dirty:
        current.dirty = True
        state.pending_metadata += 1
        current = current.parent


def forget_dirty(state: VolumeState, node: Node) -> None:
    if node.dirty:
        node.dirty = False
        state.pending_metadata -= 1


def spare_blocks(state: VolumeState, newly_dirty: int, frees_space: bool) -> int:
    committed = state.pending_metadata + newly_dirty
    if not frees_space:
        committed += state.reserve
    return state.allocator.free - committed


def require_space(state: VolumeState, blocks: int, newly_dirty: int, frees_space: bool) -> None:
    if spare_blocks(state, newly_dirty, frees_space) < blocks:
        raise KernelError(NO_SPACE, "the volume has no room left for the operation")
