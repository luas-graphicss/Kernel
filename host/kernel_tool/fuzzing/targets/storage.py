import functools

from kernel_protocol.errors.codes import KernelError
from kernel_protocol.services.files import MAX_PATH_COMPONENTS
from kernel_services.filesystem.backends.boot import BootBackend
from kernel_services.filesystem.format.blocks import decode_block
from kernel_services.filesystem.format.directory import decode_entries
from kernel_services.filesystem.format.index import decode_index
from kernel_services.filesystem.format.layout import (
    BLOCK_BYTES,
    DIRECTORY_MAGIC,
    INDEX_FANOUT,
    INDEX_MAGIC,
    KIND_DIRECTORY,
    KIND_FILE,
)
from kernel_services.filesystem.format.names import is_utf8, name_is_valid
from kernel_services.filesystem.format.superblock import decode_superblock
from kernel_services.filesystem.namespace.paths import split
from kernel_services.filesystem.recovery.mount import mount
from kernel_services.filesystem.volume import Volume
from kernel_tool.corpus.recipes import RECIPES
from kernel_tool.fuzzing.model import Family, InterpretedTarget, InvariantError
from kernel_tool.fuzzing.targets.patches import apply_patches
from kernel_tool.storage.boot_image import BootFile, build_image
from kernel_tool.storage.image_store import ImageStore
from kernel_tool.storage.volumes import Verdict, list_tree, verify_image

MAX_SCRIPT_BYTES = 512
MAX_METADATA_BYTES = 4200
MAX_PATH_INPUT_BYTES = 1200
READABLE = (Verdict.MOUNTABLE, Verdict.READ_ONLY)
PROBE_NAME = b"fuzzing-probe"
PROBE_CONTENT = bytes(range(256)) * 24
SEED_RUNTIME = b"micropython-1.29"
DEVICE_BLOCKS = 64
DECODERS = 4
GENERATION_BYTES = 8
SUPERBLOCK_SLOTS = 2
BOOT_FILES = (
    BootFile("system/config", b'[system]\nversion = 1\nname = "kernel"\n'),
    BootFile("apps/sysinfo.py", b"print('sysinfo')\n"),
    BootFile("apps/notes/readme", bytes(range(256)) * 20),
)


@functools.cache
def volume_images() -> tuple[bytes, ...]:
    return tuple(RECIPES[name]() for name in sorted(RECIPES))


@functools.cache
def boot_images() -> tuple[bytes, ...]:
    return (build_image(BOOT_FILES, SEED_RUNTIME), build_image((), SEED_RUNTIME))


@functools.cache
def reference_device() -> ImageStore:
    return ImageStore(bytes(DEVICE_BLOCKS * BLOCK_BYTES))


def volume_seeds() -> tuple[bytes, ...]:
    return tuple(bytes((index,)) for index in range(len(volume_images())))


def mount_edited_volume(data: bytes) -> None:
    if not data:
        return
    images = volume_images()
    image = apply_patches(images[data[0] % len(images)], data[1:])
    report = verify_image(image)
    if report.verdict not in READABLE:
        return
    try:
        list_tree(image)
    except KernelError as error:
        raise InvariantError("a volume that passed the deep check cannot be listed") from error
    if report.verdict is Verdict.MOUNTABLE:
        write_after_mount(image)


def write_after_mount(image: bytes) -> None:
    store = ImageStore(image)
    volume = Volume(store, mount(store, True))
    if volume.is_read_only():
        return
    try:
        probe = volume.create(volume.root(), PROBE_NAME, KIND_FILE)
        volume.write(probe, 0, PROBE_CONTENT)
        volume.sync()
    except KernelError:
        written = False
    else:
        written = True
    after = verify_image(bytes(store.content))
    if after.verdict not in READABLE:
        raise InvariantError("a write to a mounted volume left an image that does not mount")
    if written and after.verdict is not Verdict.MOUNTABLE:
        raise InvariantError("a commit that reported success left a volume that is not writable")


def metadata_seeds() -> tuple[bytes, ...]:
    return tuple(bytes((decoder,)) + bytes(64) for decoder in range(DECODERS))


def decode_metadata(data: bytes) -> None:
    if len(data) < 2 + GENERATION_BYTES:
        return
    decoder, option, body = data[0] % DECODERS, data[1], data[2:]
    if decoder == 0:
        decode_entries(body)
    elif decoder == 1:
        expected = int.from_bytes(body[:2], "little") % (INDEX_FANOUT + 2)
        decode_index(body[2:], expected)
    elif decoder == 2:
        magic = DIRECTORY_MAGIC if option % 2 else INDEX_MAGIC
        newest = int.from_bytes(body[:GENERATION_BYTES], "little")
        decode_block(_whole_block(body[GENERATION_BYTES:]), magic, newest)
    else:
        decode_superblock(_whole_block(body), option % SUPERBLOCK_SLOTS, reference_device())


def path_seeds() -> tuple[bytes, ...]:
    return (
        b"data/journey/note",
        b"boot/../data/./notes//entry.txt",
        "data/caf\u00e9/\u65e5\u672c".encode(),
        b"../outside",
        b"a/" * 40,
    )


def resolve_path(data: bytes) -> None:
    if is_utf8(data) != _is_standard_utf8(data):
        raise InvariantError("the name check and the UTF-8 standard disagree about a byte sequence")
    components = split(data)
    if len(components) > MAX_PATH_COMPONENTS:
        raise InvariantError("a path was accepted with more components than the limit")
    if not all(name_is_valid(component) for component in components):
        raise InvariantError("a path was accepted with a component that is not a valid name")


def boot_image_seeds() -> tuple[bytes, ...]:
    return tuple(bytes((index,)) for index in range(len(boot_images())))


def read_edited_boot_image(data: bytes) -> None:
    if not data:
        return
    images = boot_images()
    image = apply_patches(images[data[0] % len(images)], data[1:])
    backend = BootBackend(ImageStore(image), SEED_RUNTIME)
    pending = [backend.root()]
    while pending:
        directory = pending.pop()
        for name, kind, size in backend.listing(directory):
            node = backend.lookup(directory, name)
            if kind == KIND_DIRECTORY:
                pending.append(node)
            else:
                backend.read(node, 0, size)


def _whole_block(content: bytes) -> bytes:
    return content[:BLOCK_BYTES] + bytes(BLOCK_BYTES - min(len(content), BLOCK_BYTES))


def _is_standard_utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


TARGETS = (
    InterpretedTarget(
        name="volume-image",
        family=Family.STORAGE,
        sources=("src/kernel_services/filesystem",),
        max_input_bytes=MAX_SCRIPT_BYTES,
        seeds=volume_seeds,
        run=mount_edited_volume,
    ),
    InterpretedTarget(
        name="volume-metadata",
        family=Family.STORAGE,
        sources=("src/kernel_services/filesystem/format",),
        max_input_bytes=MAX_METADATA_BYTES,
        seeds=metadata_seeds,
        run=decode_metadata,
        refusals=(KernelError,),
    ),
    InterpretedTarget(
        name="paths",
        family=Family.STORAGE,
        sources=(
            "src/kernel_services/filesystem/namespace/paths.py",
            "src/kernel_services/filesystem/format/names.py",
        ),
        max_input_bytes=MAX_PATH_INPUT_BYTES,
        seeds=path_seeds,
        run=resolve_path,
        refusals=(KernelError,),
    ),
    InterpretedTarget(
        name="boot-image",
        family=Family.STORAGE,
        sources=(
            "src/kernel_services/filesystem/boot",
            "src/kernel_services/filesystem/backends/boot.py",
        ),
        max_input_bytes=MAX_SCRIPT_BYTES,
        seeds=boot_image_seeds,
        run=read_edited_boot_image,
        refusals=(KernelError,),
    ),
)
