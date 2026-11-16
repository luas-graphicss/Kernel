from kernel_protocol.errors.codes import LIMIT_EXCEEDED, NO_SPACE, KernelError
from kernel_services.filesystem.format.codec import smaller
from kernel_services.filesystem.format.index import blocks_for
from kernel_services.filesystem.format.layout import BLOCK_BYTES, MAX_FILE_BYTES, NO_BLOCK
from kernel_services.filesystem.storage import read_verified
from kernel_services.filesystem.transactions.nodes import FileNode
from kernel_services.filesystem.transactions.state import (
    VolumeState,
    clean_ancestors,
    mark_dirty,
    require_space,
    spare_blocks,
)

FILE_TOO_LARGE = "file would exceed the largest file of the format"


def block_content(state: VolumeState, file: FileNode, index: int) -> bytes:
    block = file.map.blocks[index] if index < len(file.map.blocks) else NO_BLOCK
    if block == NO_BLOCK:
        return bytes(BLOCK_BYTES)
    return read_verified(state.store, block, file.map.checksums[index])


def needs_block(state: VolumeState, file: FileNode, index: int) -> bool:
    if index >= len(file.map.blocks) or file.map.blocks[index] == NO_BLOCK:
        return True
    return not state.allocator.is_fresh(file.map.blocks[index])


def store_block(state: VolumeState, file: FileNode, index: int, content: bytes) -> None:
    current = file.map.blocks[index] if index < len(file.map.blocks) else NO_BLOCK
    target = current
    if needs_block(state, file, index):
        target = state.allocator.allocate()
    try:
        state.store.write(target, content)
    except KernelError:
        if target != current:
            state.allocator.release(target)
        raise
    if target != current and current != NO_BLOCK:
        state.allocator.release(current)
    if index >= len(file.map.blocks):
        file.map.resize(index + 1)
    file.map.blocks[index] = target
    file.map.checksums[index] = state.store.checksum(content)


def affordable_end(state: VolumeState, file: FileNode, offset: int, end: int) -> int:
    spare = spare_blocks(state, clean_ancestors(file), False)
    index = offset // BLOCK_BYTES
    while index * BLOCK_BYTES < end:
        if needs_block(state, file, index):
            if spare <= 0:
                return smaller(end, index * BLOCK_BYTES)
            spare -= 1
        index += 1
    return end


def read(state: VolumeState, file: FileNode, offset: int, count: int) -> bytes:
    end = smaller(offset + count, file.size)
    parts = []
    position = offset
    while position < end:
        start = position % BLOCK_BYTES
        length = smaller(BLOCK_BYTES - start, end - position)
        content = block_content(state, file, position // BLOCK_BYTES)
        parts.append(content[start : start + length])
        position += length
    return b"".join(parts)


def write(state: VolumeState, file: FileNode, offset: int, data: bytes) -> int:
    if offset + len(data) > MAX_FILE_BYTES:
        raise KernelError(LIMIT_EXCEEDED, FILE_TOO_LARGE)
    if len(data) == 0:
        return 0
    end = affordable_end(state, file, offset, offset + len(data))
    if end <= offset:
        raise KernelError(NO_SPACE, "the volume has no room left for the data")
    mark_dirty(state, file)
    position = offset
    while position < end:
        start = position % BLOCK_BYTES
        length = smaller(BLOCK_BYTES - start, end - position)
        chunk = data[position - offset : position - offset + length]
        if length != BLOCK_BYTES:
            base = block_content(state, file, position // BLOCK_BYTES)
            chunk = base[:start] + chunk + base[start + length :]
        store_block(state, file, position // BLOCK_BYTES, chunk)
        position += length
        if position > file.size:
            file.size = position
    return end - offset


def truncate(state: VolumeState, file: FileNode, size: int) -> None:
    kept = blocks_for(size)
    tail = size % BLOCK_BYTES
    shrinks = size < file.size
    if size > MAX_FILE_BYTES:
        raise KernelError(LIMIT_EXCEEDED, FILE_TOO_LARGE)
    if size == file.size:
        return
    rewrites = shrinks and tail != 0 and file.map.blocks[kept - 1] != NO_BLOCK
    needed = 1 if rewrites and needs_block(state, file, kept - 1) else 0
    require_space(state, needed, clean_ancestors(file), shrinks)
    mark_dirty(state, file)
    if rewrites:
        content = block_content(state, file, kept - 1)
        store_block(state, file, kept - 1, content[:tail] + bytes(BLOCK_BYTES - tail))
    for index in range(kept, len(file.map.blocks)):
        if file.map.blocks[index] != NO_BLOCK:
            state.allocator.release(file.map.blocks[index])
    file.map.resize(kept)
    file.size = size
