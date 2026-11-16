from collections.abc import Callable

from kernel_services.filesystem.format.layout import KIND_DIRECTORY, KIND_FILE
from kernel_services.filesystem.transactions.nodes import Node
from kernel_services.filesystem.volume import Volume
from kernel_tool.storage.image_store import ImageStore
from kernel_tool.storage.volumes import create_image

VOLUME_BLOCKS = 64
VOLUME = 0x4352415348
KEEP = b"keep.bin"
VICTIM = b"victim.txt"
DIRECTORY = b"dir"
EMPTY_DIRECTORY = b"empty-dir"
OLD = b"old.txt"
KEPT_CONTENT = bytes(range(250)) * 24
APPENDED = bytes(range(100, 200)) * 50
OVERWRITTEN = b"Z" * 5000
OVERWRITE_OFFSET = 100
SHORT_BYTES = 10
EXTENDED_BYTES = 20000

type Transaction = Callable[[Volume], None]


def baseline() -> bytes:
    store = ImageStore(create_image(VOLUME_BLOCKS, VOLUME))
    volume = Volume(store)
    root = volume.root()
    volume.write(volume.create(root, KEEP, KIND_FILE), 0, KEPT_CONTENT)
    volume.write(volume.create(root, VICTIM, KIND_FILE), 0, b"victim")
    directory = volume.create(root, DIRECTORY, KIND_DIRECTORY)
    old = volume.create(directory, OLD, KIND_FILE)
    volume.write(old, 0, b"old")
    volume.create(root, EMPTY_DIRECTORY, KIND_DIRECTORY)
    volume.sync()
    volume.write(old, 0, b"OLD")
    volume.sync()
    return bytes(store.content)


def at(volume: Volume, name: bytes) -> Node:
    return volume.lookup(volume.root(), name)


def create_file(volume: Volume) -> None:
    volume.create(volume.root(), b"new.txt", KIND_FILE)


def append_to_file(volume: Volume) -> None:
    volume.write(at(volume, KEEP), len(KEPT_CONTENT), APPENDED)


def overwrite_file_range(volume: Volume) -> None:
    volume.write(at(volume, KEEP), OVERWRITE_OFFSET, OVERWRITTEN)


def truncate_file(volume: Volume) -> None:
    volume.truncate(at(volume, KEEP), SHORT_BYTES)


def extend_file(volume: Volume) -> None:
    volume.truncate(at(volume, KEEP), EXTENDED_BYTES)


def make_directory(volume: Volume) -> None:
    volume.create(volume.root(), b"new-dir", KIND_DIRECTORY)


def rename_file(volume: Volume) -> None:
    volume.rename(volume.root(), VICTIM, volume.root(), b"renamed.txt")


def rename_over_file(volume: Volume) -> None:
    volume.rename(volume.root(), VICTIM, volume.root(), KEEP)


def move_into_directory(volume: Volume) -> None:
    volume.rename(volume.root(), VICTIM, at(volume, DIRECTORY), VICTIM)


def remove_file(volume: Volume) -> None:
    volume.remove(volume.root(), VICTIM)


def remove_directory(volume: Volume) -> None:
    volume.remove(volume.root(), EMPTY_DIRECTORY)


TRANSACTIONS: tuple[tuple[str, Transaction], ...] = (
    ("create-file", create_file),
    ("append-to-file", append_to_file),
    ("overwrite-file-range", overwrite_file_range),
    ("truncate-file", truncate_file),
    ("extend-file", extend_file),
    ("make-directory", make_directory),
    ("rename-file", rename_file),
    ("rename-over-file", rename_over_file),
    ("move-into-directory", move_into_directory),
    ("remove-file", remove_file),
    ("remove-directory", remove_directory),
)
