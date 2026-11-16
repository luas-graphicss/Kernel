from kernel_services.filesystem.format.codec import put
from kernel_services.filesystem.format.layout import BLOCK_BYTES, KIND_DIRECTORY
from kernel_services.filesystem.transactions.nodes import Node
from kernel_services.filesystem.volume import Volume

SEPARATOR = b"/"


def file_digest(volume: Volume, file: Node, size: int, digest: int) -> int:
    offset = 0
    while offset < size:
        digest = volume.checksum(volume.read(file, offset, BLOCK_BYTES), digest)
        offset += BLOCK_BYTES
    return digest


def tree_digest(volume: Volume) -> int:
    digest = 0
    pending: list[tuple[bytes, Node]] = [(b"", volume.root())]
    while pending:
        path, directory = pending.pop()
        for name, kind, size in volume.listing(directory):
            described = path + SEPARATOR + name
            node = volume.lookup(directory, name)
            digest = volume.checksum(described + put(kind, 1) + put(size, 8), digest)
            if kind == KIND_DIRECTORY:
                pending.append((described, node))
            else:
                digest = file_digest(volume, node, size, digest)
    return digest
