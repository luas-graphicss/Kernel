import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kernel_protocol.errors.codes import KernelError
from kernel_services.filesystem.backends.boot import BootBackend
from kernel_services.filesystem.boot.layout import (
    ABI_VERSION,
    BLOCK_BYTES,
    FIRST_TABLE_BLOCK,
    MAX_ENTRIES,
    MAX_FILE_BYTES,
    Entry,
    Header,
    blocks_for,
    encode_header,
    encode_table,
    path_is_valid,
)
from kernel_services.filesystem.format.layout import KIND_DIRECTORY
from kernel_tool.outcome import CheckError
from kernel_tool.storage.image_store import ImageStore
from kernel_tool.toolchain.lock import ToolchainLock
from kernel_tool.toolchain.resolve import RUNTIME_ARTIFACT

MANIFEST = Path("config") / "boot" / "manifest.toml"
RELEASE_PATH = "system/release"
VERSION_PARTS = 2
SEPARATOR = b"/"


@dataclass(frozen=True, slots=True)
class BootFile:
    path: str
    content: bytes


def runtime_tag(lock: ToolchainLock) -> bytes:
    artifact = lock.artifact(RUNTIME_ARTIFACT)
    release = ".".join(artifact.version.split(".")[:VERSION_PARTS])
    return f"{artifact.name}-{release}".encode("ascii")


def release_file(runtime: bytes) -> BootFile:
    content = f"abi={ABI_VERSION}\nruntime={runtime.decode('ascii')}\n"
    return BootFile(RELEASE_PATH, content.encode("ascii"))


def load_files(root: Path) -> tuple[BootFile, ...]:
    manifest = root / MANIFEST
    try:
        with manifest.open("rb") as source:
            document = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise CheckError(f"{manifest}: {error}") from error
    listed = document.get("file", [])
    if not isinstance(listed, list) or set(document) - {"file"}:
        raise CheckError(f"{manifest}: only [[file]] tables are allowed")
    return tuple(_boot_file(root, manifest, entry) for entry in listed)


def build_image(files: Sequence[BootFile], runtime: bytes) -> bytes:
    ordered = sorted(files, key=lambda file: file.path.encode("utf-8"))
    _check_files(ordered)
    checksums = ImageStore(b"")
    table_bytes = len(encode_table([Entry(_path(file), 0, 0, 0) for file in ordered]))
    next_block = FIRST_TABLE_BLOCK + blocks_for(table_bytes)
    entries = []
    for file in ordered:
        entries.append(
            Entry(_path(file), next_block, len(file.content), checksums.checksum(file.content))
        )
        next_block += blocks_for(len(file.content))
    table = encode_table(entries)
    header = Header(
        abi=ABI_VERSION,
        runtime=runtime,
        entries=len(entries),
        table_bytes=len(table),
        table_checksum=checksums.checksum(table),
        total_blocks=next_block,
    )
    parts = [encode_header(header, checksums), _padded(table)]
    parts.extend(_padded(file.content) for file in ordered)
    return b"".join(parts)


def write_boot_image(root: Path, lock: ToolchainLock, output: Path) -> None:
    runtime = runtime_tag(lock)
    output.write_bytes(build_image((*load_files(root), release_file(runtime)), runtime))


def read_image(content: bytes, runtime: bytes) -> dict[str, bytes]:
    try:
        backend = BootBackend(ImageStore(content), runtime)
        return dict(_walk(backend, backend.root(), b""))
    except KernelError as error:
        raise CheckError(f"boot image refused: {error.detail}") from error


def _walk(backend: BootBackend, directory: object, prefix: bytes) -> list[tuple[str, bytes]]:
    found = []
    for name, kind, size in backend.listing(directory):
        node = backend.lookup(directory, name)
        if kind == KIND_DIRECTORY:
            found.extend(_walk(backend, node, prefix + name + SEPARATOR))
        else:
            found.append(((prefix + name).decode("utf-8"), backend.read(node, 0, size)))
    return found


def _boot_file(root: Path, manifest: Path, entry: object) -> BootFile:
    if not isinstance(entry, dict) or set(entry) != {"path", "source"}:
        raise CheckError(f"{manifest}: each [[file]] needs exactly a path and a source")
    path, source = entry["path"], entry["source"]
    if not isinstance(path, str) or not isinstance(source, str):
        raise CheckError(f"{manifest}: path and source must be strings")
    origin = (root / source).resolve()
    if not origin.is_relative_to(root.resolve()) or not origin.is_file():
        raise CheckError(f"{manifest}: source {source!r} is not a file of the repository")
    return BootFile(path, origin.read_bytes())


def _check_files(files: Sequence[BootFile]) -> None:
    if len(files) > MAX_ENTRIES:
        raise CheckError(f"a boot image holds at most {MAX_ENTRIES} files")
    paths = [_path(file) for file in files]
    for file, path in zip(files, paths, strict=True):
        if not path_is_valid(path):
            raise CheckError(f"boot file path {file.path!r} is not valid")
        if len(file.content) > MAX_FILE_BYTES:
            raise CheckError(f"boot file {file.path!r} exceeds {MAX_FILE_BYTES} bytes")
    if len(set(paths)) != len(paths):
        raise CheckError("boot files repeat a path")


def _path(file: BootFile) -> bytes:
    return file.path.encode("utf-8")


def _padded(content: bytes) -> bytes:
    return content + bytes(blocks_for(len(content)) * BLOCK_BYTES - len(content))
