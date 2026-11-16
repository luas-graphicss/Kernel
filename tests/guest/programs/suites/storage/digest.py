import _process
from kernel_client import files
from kernel_protocol.services.files import KIND_DIRECTORY, OPEN_DIRECTORY, OPEN_READ
from suites.support.platform import mount_report

SEPARATOR = b"/"
CHUNK_BYTES = 4096
DATA = b"data"


def file_digest(namespace: files.Namespace, path: bytes, size: int, digest: int) -> int:
    opened = namespace.open(path, OPEN_READ)
    offset = 0
    while offset < size:
        digest = _process.crc32(opened.read(offset, CHUNK_BYTES), digest)
        offset += CHUNK_BYTES
    opened.close()
    return digest


def tree_digest(namespace: files.Namespace, mount: bytes) -> int:
    digest = 0
    pending = [(b"", mount)]
    while pending:
        described, location = pending.pop()
        directory = namespace.open(location, OPEN_DIRECTORY)
        listed = directory.entries()
        directory.close()
        for name, kind, size in listed:
            entry = described + SEPARATOR + name
            target = location + SEPARATOR + name
            summary = entry + kind.to_bytes(1, "little") + size.to_bytes(8, "little")
            digest = _process.crc32(summary, digest)
            if kind == KIND_DIRECTORY:
                pending.append((entry, target))
            else:
                digest = file_digest(namespace, target, size, digest)
    return digest


def report_volume(namespace: files.Namespace) -> None:
    generation = mount_report(namespace, DATA).generation
    digest = tree_digest(namespace, DATA)
    print(f"storage: volume generation={generation} digest={digest:08x}")
