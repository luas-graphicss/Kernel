from pathlib import Path

from kernel_tool.build.native import BuildOutputs
from kernel_tool.outcome import CheckError
from kernel_tool.scenarios.model import BootEntry
from kernel_tool.storage.boot_image import (
    BootFile,
    build_image,
    load_files,
    release_file,
    runtime_tag,
)
from kernel_tool.toolchain.lock import load_lock
from kernel_tool.workspace import LOCK_FILE_NAME

OVERLAY_IMAGE = "boot-overlay.img"


def boot_volume_file(
    overlay: tuple[BootEntry, ...], root: Path, outputs: BuildOutputs, directory: Path
) -> Path:
    if not overlay:
        return outputs.boot_image
    runtime = runtime_tag(load_lock(root / LOCK_FILE_NAME))
    files = {file.path: file for file in (*load_files(root), release_file(runtime))}
    for entry in overlay:
        if entry.source is None:
            files.pop(entry.path, None)
        else:
            files[entry.path] = BootFile(entry.path, _content(root, entry.source))
    image = directory / OVERLAY_IMAGE
    image.write_bytes(build_image(tuple(files.values()), runtime))
    return image


def _content(root: Path, source: str) -> bytes:
    try:
        return (root / source).read_bytes()
    except OSError as error:
        raise CheckError(f"cannot read the boot file {source}: {error}") from error
